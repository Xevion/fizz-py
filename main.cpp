#include <fizz/client/AsyncFizzClient.h>
#include <iostream>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
// #include <pybind11/complex.h>

namespace py = pybind11;

int add(int i, int j) {
    return i + j;
}

auto versions() {
  auto context = fizz::client::FizzClientContext();
  context.setSupportedVersions({fizz::ProtocolVersion::tls_1_3_26_fb, fizz::ProtocolVersion::tls_1_3_28, fizz::ProtocolVersion::tls_1_3});
  return context.getSupportedVersions();
}

PYBIND11_MODULE(fizzpy, m) {
    m.doc() = "C++ Bindings for Fizz, a TLS 1.3 library from Facebook"; // optional module docstring

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

    m.def("add", &add, "A function that adds two numbers");
    m.def("versions", &versions, "A function that returns the supported versions");
}

int main() {
  auto context = fizz::client::FizzClientContext();
  std::cout << toString(context.getSupportedVersions()[0]) << std::endl;
}