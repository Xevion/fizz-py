- Python 3.10
- cmake 3.22.1

```bash
git clone https://github.com/Xevion/fizz-py --recursive
cd fizz-py
git submodule update --init --recursive # Ensure submodules are available (if you forgot to clone recursively)
./vcpkg/bootstrap-vcpkg.sh
./vcpkg/vcpkg install
pip3 install ./
```

VCPKG_ROOT="./vcpkg" cmake --preset=default && cmake --build build