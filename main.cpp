#include <fizz/client/AsyncFizzClient.h>
#include <iostream>

int main() {
  auto context = fizz::client::FizzClientContext();
  std::cout << toString(context.getSupportedVersions()[0]) << std::endl;
}