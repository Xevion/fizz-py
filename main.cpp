#include <iostream>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <fizz/client/FizzClientContext.h>
// #include <pybind11/complex.h>

namespace py = pybind11;

// int add(int i, int j) {
//     return i + j;
// }

PYBIND11_MODULE(fizzpy, m)
{
  m.doc() = "Python Bindings for Fizz, a TLS 1.3 library from Facebook"; // optional module docstring

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
      .value("fizz_secp256r1", fizz::NamedGroup::secp256r1)
      .value("fizz_secp384r1", fizz::NamedGroup::secp384r1)
      .value("fizz_secp521r1", fizz::NamedGroup::secp521r1)
      .value("fizz_x25519", fizz::NamedGroup::x25519)
      .value("fizz_x25519_kyber768_draft00", fizz::NamedGroup::x25519_kyber768_draft00)
      .value("fizz_secp256r1_kyber768_draft00", fizz::NamedGroup::secp256r1_kyber768_draft00)
      .value("fizz_x25519_kyber768_experimental", fizz::NamedGroup::x25519_kyber768_experimental)
      .value("fizz_x25519_kyber512_experimental", fizz::NamedGroup::x25519_kyber512_experimental)
      .value("fizz_secp521r1_x25519", fizz::NamedGroup::secp521r1_x25519)
      .value("fizz_x25519_kyber512", fizz::NamedGroup::x25519_kyber512)
      .value("fizz_secp256r1_kyber512", fizz::NamedGroup::secp256r1_kyber512)
      .value("fizz_kyber512", fizz::NamedGroup::kyber512)
      .value("fizz_secp384r1_kyber768", fizz::NamedGroup::secp384r1_kyber768)
      .export_values();

      py::enum_<fizz::PskKeyExchangeMode>(m, "PskKeyExchangeMode")
        .value("psk_ke", fizz::PskKeyExchangeMode::psk_ke)
        .value("psk_dhe_ke", fizz::PskKeyExchangeMode::psk_dhe_ke)
        .export_values();

      py::enum_<fizz::CipherSuite>(m, "CipherSuite")
        .value("TLS_AES_128_GCM_SHA256", fizz::CipherSuite::TLS_AES_128_GCM_SHA256)
        .value("TLS_AES_256_GCM_SHA384", fizz::CipherSuite::TLS_AES_256_GCM_SHA384)
        .value("TLS_CHACHA20_POLY1305_SHA256", fizz::CipherSuite::TLS_CHACHA20_POLY1305_SHA256)
        .value("TLS_AEGIS_256_SHA512", fizz::CipherSuite::TLS_AEGIS_256_SHA512)
        .value("TLS_AEGIS_128L_SHA256", fizz::CipherSuite::TLS_AEGIS_128L_SHA256)
        .value("TLS_AES_128_OCB_SHA256_EXPERIMENTAL", fizz::CipherSuite::TLS_AES_128_OCB_SHA256_EXPERIMENTAL)
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
      .value("ecdsa_secp256r1_sha256_batch", fizz::SignatureScheme::ecdsa_secp256r1_sha256_batch)
      .value("ecdsa_secp384r1_sha384_batch", fizz::SignatureScheme::ecdsa_secp384r1_sha384_batch)
      .value("ecdsa_secp521r1_sha512_batch", fizz::SignatureScheme::ecdsa_secp521r1_sha512_batch)
      .value("ed25519_batch", fizz::SignatureScheme::ed25519_batch)
      .value("ed448_batch", fizz::SignatureScheme::ed448_batch)
      .value("rsa_pss_sha256_batch", fizz::SignatureScheme::rsa_pss_sha256_batch)
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
      .def("setDefaultShares", &fizz::client::FizzClientContext::setDefaultShares)
      .def("getDefaultShares", &fizz::client::FizzClientContext::getDefaultShares)
      .def("setSupportedPskModes", &fizz::client::FizzClientContext::setSupportedPskModes)
      .def("getSupportedPskModes", &fizz::client::FizzClientContext::getSupportedPskModes)
      .def("setSupportedAlpns", &fizz::client::FizzClientContext::setSupportedAlpns)
      .def("getSupportedAlpns", &fizz::client::FizzClientContext::getSupportedAlpns);

  // m.def("add", &add, "A function that adds two numbers");
  // m.def("versions", &versions, "A function that returns the supported versions");
}