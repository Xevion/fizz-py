- Python 3.10
- cmake 3.22.1

```bash
git submodule update --init --recursive # Ensure submodules are available
./vcpkg/bootstrap-vcpkg.sh
./vcpkg/vcpkg install
pip3 install ./
```

VCPKG_ROOT="./vcpkg" cmake --preset=default && cmake --build build