#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <fizz/client/AsyncFizzClient.h>
#include <fizz/client/FizzClientContext.h>
#include <fizz/protocol/DefaultCertificateVerifier.h>
#include <fizz/tool/CertificateVerifiers.h>

#include <folly/SocketAddress.h>
#include <folly/io/IOBuf.h>
#include <folly/io/async/EventBase.h>
#include <folly/io/async/ScopedEventBaseThread.h>

#include <deque>
#include <memory>
#include <optional>
#include <string>

namespace py = pybind11;

namespace {

// One background thread runs the folly EventBase that drives every connection.
// Fizz is callback-driven on this loop; the Python facades never touch it
// directly — they schedule work here and are resolved via Python callables.
folly::EventBase* sharedEvb() {
  static folly::ScopedEventBaseThread thread("fizzpy-evb");
  return thread.getEventBase();
}

// Holds the resolve/reject pair for one pending async op. py::function refcounts
// are only ever touched while the GIL is held — callers MUST hold the GIL when
// constructing, calling, moving-from, or destroying a live pair.
struct Promise {
  py::function resolve;
  py::function reject;
};

// Build a Python exception object carrying `msg` (GIL must be held).
py::object makeError(const std::string& msg) {
  return py::module_::import("builtins").attr("ConnectionError")(msg);
}

} // namespace

// A single TLS 1.3 connection. Owns an AsyncFizzClient living on the shared
// EventBase thread. All Fizz interaction happens on that thread; Python threads
// only schedule work and receive results through resolve/reject callables.
//
// The object implements ReadCallback itself (long-lived, one reader per
// connection). Connect and write use short-lived heap callbacks that delete
// themselves while holding the GIL.
class TlsConnection : public folly::AsyncTransportWrapper::ReadCallback {
 public:
  TlsConnection() : evb_(sharedEvb()) {}

  ~TlsConnection() override {
    // The Fizz client must be destroyed on the EventBase thread (it is a
    // DelayedDestruction). Block until teardown completes; GIL is released so
    // the loop thread can run.
    py::gil_scoped_release release;
    evb_->runInEventBaseThreadAndWait([this] {
      if (client_) {
        client_->setReadCB(nullptr);
        client_->closeNow();
        client_.reset();
      }
    });
    // pendingRead_ may still hold py::functions; clear them under the GIL.
    if (pendingRead_) {
      py::gil_scoped_acquire acquire;
      pendingRead_.reset();
    }
  }

  // Establish TCP + TLS to host:port. Resolves with None on handshake success,
  // rejects with ConnectionError otherwise.
  void connect(
      const std::string& host,
      uint16_t port,
      const std::string& sni,
      std::vector<std::string> alpns,
      bool verify,
      uint32_t timeoutMs,
      py::function resolve,
      py::function reject) {
    auto promise = std::make_shared<Promise>(
        Promise{std::move(resolve), std::move(reject)});
    auto alpnsPtr = std::make_shared<std::vector<std::string>>(std::move(alpns));

    evb_->runInEventBaseThread([this,
                                host,
                                port,
                                sni,
                                alpnsPtr,
                                verify,
                                timeoutMs,
                                promise]() mutable {
      try {
        auto ctx = std::make_shared<fizz::client::FizzClientContext>();
        if (!alpnsPtr->empty()) {
          ctx->setSupportedAlpns(*alpnsPtr);
        }

        std::shared_ptr<const fizz::CertificateVerifier> verifier;
        if (verify) {
          fizz::Error err;
          std::unique_ptr<fizz::DefaultCertificateVerifier> v;
          auto st = fizz::DefaultCertificateVerifier::create(
              v, err, fizz::VerificationContext::Client, nullptr);
          if (st != fizz::Status::Success || !v) {
            rejectOnLoop(promise, "failed to build certificate verifier");
            return;
          }
          verifier = std::move(v);
        } else {
          verifier = std::make_shared<fizz::InsecureAcceptAnyCertificate>();
        }

        client_ = fizz::client::AsyncFizzClient::UniquePtr(
            new fizz::client::AsyncFizzClient(evb_, ctx));

        folly::SocketAddress addr(host, port, /*allowNameLookup=*/true);
        auto* cb = new ConnectCb(this, promise);
        client_->connect(
            addr,
            cb,
            verifier,
            folly::Optional<std::string>(sni),
            folly::Optional<std::string>(),
            std::chrono::milliseconds(timeoutMs),
            std::chrono::milliseconds(timeoutMs));
      } catch (const std::exception& e) {
        rejectOnLoop(promise, std::string("connect failed: ") + e.what());
      }
    });
  }

  // Send application bytes. Resolves with None on flush, rejects on error.
  void write(py::bytes data, py::function resolve, py::function reject) {
    std::string bytes = data; // copy out under GIL
    auto promise = std::make_shared<Promise>(
        Promise{std::move(resolve), std::move(reject)});
    evb_->runInEventBaseThread(
        [this, bytes = std::move(bytes), promise]() mutable {
          if (!client_ || !client_->good()) {
            rejectOnLoop(promise, "connection not open");
            return;
          }
          auto* cb = new WriteCb(promise);
          client_->writeChain(cb, folly::IOBuf::copyBuffer(bytes));
        });
  }

  // Read the next chunk of decrypted application bytes. Resolves with bytes
  // (empty bytes == EOF), rejects on transport error. At most one read may be
  // outstanding at a time.
  void read(py::function resolve, py::function reject) {
    auto promise = std::make_shared<Promise>(
        Promise{std::move(resolve), std::move(reject)});
    evb_->runInEventBaseThread([this, promise]() mutable {
      if (!buffer_.empty()) {
        fulfillRead(promise);
        return;
      }
      if (readErr_) {
        rejectOnLoop(promise, *readErr_);
        return;
      }
      if (eof_) {
        resolveBytes(promise, std::string());
        return;
      }
      pendingRead_ = std::move(*promise);
    });
  }

  // Negotiated TLS parameters, valid after connect resolves. Reads cached
  // fields set on the loop thread before the connect promise fired.
  py::dict negotiated() {
    py::dict d;
    d["version"] = negVersion_;
    d["cipher"] = negCipher_;
    d["group"] = negGroup_;
    d["group_code"] = negGroupCode_;
    d["alpn"] = negAlpn_;
    d["sni"] = negSni_;
    d["peer_cert"] = negPeerCert_;
    return d;
  }

  void close() {
    evb_->runInEventBaseThread([this] {
      if (client_) {
        client_->setReadCB(nullptr);
        client_->closeNow();
      }
    });
  }

  // ReadCallback (movable-buffer mode) — invoked on the EventBase thread.
  bool isBufferMovable() noexcept override {
    return true;
  }

  void getReadBuffer(void**, size_t*) noexcept override {
    // Unused: movable-buffer mode delivers IOBufs via readBufferAvailable.
  }

  void readDataAvailable(size_t) noexcept override {
    // Unused in movable-buffer mode.
  }

  void readBufferAvailable(std::unique_ptr<folly::IOBuf> buf) noexcept override {
    if (buf) {
      buf->coalesce();
      buffer_.push_back(std::move(buf));
    }
    if (pendingRead_) {
      auto p = std::make_shared<Promise>(std::move(*pendingRead_));
      pendingRead_.reset();
      fulfillRead(p);
    }
  }

  void readEOF() noexcept override {
    eof_ = true;
    if (pendingRead_) {
      auto p = std::make_shared<Promise>(std::move(*pendingRead_));
      pendingRead_.reset();
      resolveBytes(p, std::string());
    }
  }

  void readErr(const folly::AsyncSocketException& ex) noexcept override {
    readErr_ = std::string("read error: ") + ex.what();
    if (pendingRead_) {
      auto p = std::make_shared<Promise>(std::move(*pendingRead_));
      pendingRead_.reset();
      rejectOnLoop(p, *readErr_);
    }
  }

 private:
  // Per-connect callback: drives connectSuccess/connectErr, captures negotiated
  // parameters, then installs this connection as the read callback.
  struct ConnectCb : public folly::AsyncSocket::ConnectCallback {
    TlsConnection* conn;
    std::shared_ptr<Promise> promise;
    ConnectCb(TlsConnection* c, std::shared_ptr<Promise> p)
        : conn(c), promise(std::move(p)) {}

    void connectSuccess() noexcept override {
      conn->captureNegotiated();
      conn->client_->setReadCB(conn);
      py::gil_scoped_acquire gil;
      auto resolve = std::move(promise->resolve);
      promise.reset();
      resolve(py::none());
      delete this;
    }

    void connectErr(const folly::AsyncSocketException& ex) noexcept override {
      py::gil_scoped_acquire gil;
      auto reject = std::move(promise->reject);
      promise.reset();
      reject(makeError(std::string("handshake failed: ") + ex.what()));
      delete this;
    }
  };

  struct WriteCb : public folly::AsyncTransportWrapper::WriteCallback {
    std::shared_ptr<Promise> promise;
    explicit WriteCb(std::shared_ptr<Promise> p) : promise(std::move(p)) {}

    void writeSuccess() noexcept override {
      py::gil_scoped_acquire gil;
      auto resolve = std::move(promise->resolve);
      promise.reset();
      resolve(py::none());
      delete this;
    }

    void writeErr(size_t, const folly::AsyncSocketException& ex) noexcept
        override {
      py::gil_scoped_acquire gil;
      auto reject = std::move(promise->reject);
      promise.reset();
      reject(makeError(std::string("write failed: ") + ex.what()));
      delete this;
    }
  };

  // Capture negotiated parameters into cached fields (on the loop thread,
  // before the connect promise resolves — establishing happens-before).
  void captureNegotiated() {
    if (auto v = client_->getState().version()) {
      negVersion_ = fizz::toString(*v);
    }
    if (auto c = client_->getCipher()) {
      negCipher_ = fizz::toString(*c);
    }
    if (auto g = client_->getGroup()) {
      negGroup_ = fizz::toString(*g);
      negGroupCode_ = static_cast<uint16_t>(*g);
    }
    negAlpn_ = client_->getApplicationProtocol();
    if (auto s = client_->getState().sni()) {
      negSni_ = *s;
    }
    if (const auto* cert = client_->getPeerCertificate()) {
      negPeerCert_ = cert->getIdentity();
    }
  }

  // Coalesce all buffered chunks into one bytes result and resolve.
  void fulfillRead(std::shared_ptr<Promise> promise) {
    std::string out;
    for (auto& buf : buffer_) {
      out.append(reinterpret_cast<const char*>(buf->data()), buf->length());
    }
    buffer_.clear();
    resolveBytes(promise, out);
  }

  void resolveBytes(std::shared_ptr<Promise> promise, const std::string& data) {
    py::gil_scoped_acquire gil;
    auto resolve = std::move(promise->resolve);
    promise->reject = py::function();
    resolve(py::bytes(data));
  }

  void rejectOnLoop(std::shared_ptr<Promise> promise, const std::string& msg) {
    py::gil_scoped_acquire gil;
    auto reject = std::move(promise->reject);
    promise->resolve = py::function();
    reject(makeError(msg));
  }

  folly::EventBase* evb_;
  fizz::client::AsyncFizzClient::UniquePtr client_;

  std::deque<std::unique_ptr<folly::IOBuf>> buffer_;
  std::optional<Promise> pendingRead_;
  bool eof_{false};
  std::optional<std::string> readErr_;

  std::string negVersion_;
  std::string negCipher_;
  std::string negGroup_;
  uint16_t negGroupCode_{0};
  std::string negAlpn_;
  std::string negSni_;
  std::string negPeerCert_;
};

PYBIND11_MODULE(_core, m) {
  m.doc() = "Low-level Fizz TLS 1.3 client core for fizzpy";

  py::enum_<fizz::ProtocolVersion>(m, "ProtocolVersion")
      .value("tls_1_0", fizz::ProtocolVersion::tls_1_0)
      .value("tls_1_1", fizz::ProtocolVersion::tls_1_1)
      .value("tls_1_2", fizz::ProtocolVersion::tls_1_2)
      .value("tls_1_3", fizz::ProtocolVersion::tls_1_3)
      .value("tls_1_3_23", fizz::ProtocolVersion::tls_1_3_23)
      .value("tls_1_3_23_fb", fizz::ProtocolVersion::tls_1_3_23_fb)
      .value("tls_1_3_26", fizz::ProtocolVersion::tls_1_3_26)
      .value("tls_1_3_26_fb", fizz::ProtocolVersion::tls_1_3_26_fb)
      .value("tls_1_3_28", fizz::ProtocolVersion::tls_1_3_28)
      .export_values();

  py::enum_<fizz::NamedGroup>(m, "NamedGroup")
      .value("secp256r1", fizz::NamedGroup::secp256r1)
      .value("secp384r1", fizz::NamedGroup::secp384r1)
      .value("secp521r1", fizz::NamedGroup::secp521r1)
      .value("x25519", fizz::NamedGroup::x25519)
      .value("x448", fizz::NamedGroup::x448)
      .value("mlkem512", fizz::NamedGroup::MLKEM512)
      .value("mlkem768", fizz::NamedGroup::MLKEM768)
      .value("mlkem1024", fizz::NamedGroup::MLKEM1024)
      .value("secp256r1_mlkem768", fizz::NamedGroup::SecP256r1MLKEM768)
      .value("x25519_mlkem768", fizz::NamedGroup::X25519MLKEM768)
      .export_values();

  py::enum_<fizz::PskKeyExchangeMode>(m, "PskKeyExchangeMode")
      .value("psk_ke", fizz::PskKeyExchangeMode::psk_ke)
      .value("psk_dhe_ke", fizz::PskKeyExchangeMode::psk_dhe_ke)
      .export_values();

  py::enum_<fizz::CipherSuite>(m, "CipherSuite")
      .value("TLS_AES_128_GCM_SHA256", fizz::CipherSuite::TLS_AES_128_GCM_SHA256)
      .value("TLS_AES_256_GCM_SHA384", fizz::CipherSuite::TLS_AES_256_GCM_SHA384)
      .value(
          "TLS_CHACHA20_POLY1305_SHA256",
          fizz::CipherSuite::TLS_CHACHA20_POLY1305_SHA256)
      .export_values();

  py::enum_<fizz::SignatureScheme>(m, "SignatureScheme")
      .value("ecdsa_secp256r1_sha256", fizz::SignatureScheme::ecdsa_secp256r1_sha256)
      .value("ecdsa_secp384r1_sha384", fizz::SignatureScheme::ecdsa_secp384r1_sha384)
      .value("ecdsa_secp521r1_sha512", fizz::SignatureScheme::ecdsa_secp521r1_sha512)
      .value("rsa_pss_sha256", fizz::SignatureScheme::rsa_pss_sha256)
      .value("rsa_pss_sha384", fizz::SignatureScheme::rsa_pss_sha384)
      .value("rsa_pss_sha512", fizz::SignatureScheme::rsa_pss_sha512)
      .value("ed25519", fizz::SignatureScheme::ed25519)
      .value("ed448", fizz::SignatureScheme::ed448)
      .export_values();

  py::enum_<fizz::client::SendKeyShare>(m, "SendKeyShare")
      .value("Always", fizz::client::SendKeyShare::Always)
      .value("WhenNecessary", fizz::client::SendKeyShare::WhenNecessary)
      .export_values();

  py::class_<fizz::client::FizzClientContext>(m, "FizzClientContext")
      .def(py::init<>())
      .def("setSupportedVersions", &fizz::client::FizzClientContext::setSupportedVersions)
      .def("getSupportedVersions", &fizz::client::FizzClientContext::getSupportedVersions)
      .def("setSupportedCiphers", &fizz::client::FizzClientContext::setSupportedCiphers)
      .def("getSupportedCiphers", &fizz::client::FizzClientContext::getSupportedCiphers)
      .def("setSupportedSigSchemes", &fizz::client::FizzClientContext::setSupportedSigSchemes)
      .def("getSupportedSigSchemes", &fizz::client::FizzClientContext::getSupportedSigSchemes)
      .def("setSupportedGroups", &fizz::client::FizzClientContext::setSupportedGroups)
      .def("getSupportedGroups", &fizz::client::FizzClientContext::getSupportedGroups)
      .def("setSupportedPskModes", &fizz::client::FizzClientContext::setSupportedPskModes)
      .def("getSupportedPskModes", &fizz::client::FizzClientContext::getSupportedPskModes)
      .def("setSupportedAlpns", &fizz::client::FizzClientContext::setSupportedAlpns)
      .def("getSupportedAlpns", &fizz::client::FizzClientContext::getSupportedAlpns)
      .def("setSendEarlyData", &fizz::client::FizzClientContext::setSendEarlyData)
      .def("getSendEarlyData", &fizz::client::FizzClientContext::getSendEarlyData)
      .def("setSendKeyShare", &fizz::client::FizzClientContext::setSendKeyShare)
      .def("getSendKeyShare", &fizz::client::FizzClientContext::getSendKeyShare);

  py::class_<TlsConnection>(m, "TlsConnection")
      .def(py::init<>())
      .def(
          "connect",
          &TlsConnection::connect,
          py::arg("host"),
          py::arg("port"),
          py::arg("sni"),
          py::arg("alpns"),
          py::arg("verify"),
          py::arg("timeout_ms"),
          py::arg("resolve"),
          py::arg("reject"))
      .def("write", &TlsConnection::write, py::arg("data"), py::arg("resolve"), py::arg("reject"))
      .def("read", &TlsConnection::read, py::arg("resolve"), py::arg("reject"))
      .def("negotiated", &TlsConnection::negotiated)
      .def("close", &TlsConnection::close);
}
