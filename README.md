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

`VCPKG_ROOT` is usually used as an environment variable, but it's not stable in my experience. Directly setting the `CMAKE_TOOLCHAIN_FILE` is more reliable.

### Reference Material

Repositories, files, GitHub Actions, workflows or any reference I found useful in creating this project.

[Homebrew/homebrew-core/Formula/f/fizz.rb](https://github.com/Homebrew/homebrew-core/blob/c1534daa2f467d9924d02333fd0aed8dbf17f465/Formula/f/fizz.rb#L60)
[pybind/cmake_example](https://github.com/pybind/cmake_example/tree/master)
[lukka/run-cmake](https://github.com/lukka/run-cmake)
[lukka/run-cmake](https://github.com/lukka/get-cmake)
[caiorss/example-pybind11-vcpkg](https://github.com/caiorss/example-pybind11-vcpkg)
[pybind/scikit_build_example](https://github.com/pybind/scikit_build_example)
[bloomberg/memray/.github/workflows/build_wheels.yml](https://github.com/bloomberg/memray/blob/main/.github/workflows/build_wheels.yml)