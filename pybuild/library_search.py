from ._target import colorama
import subprocess
import enum
libs = {}

class ABIS(enum.Enum):
    libcxx = 1
    libstdcpp = 2
    C = 3

def find_python(result = []):
    if result:
        return result[0]
    args = subprocess.run(['python3-config', '--ldflags', '--embed'], stdout=subprocess.PIPE).stdout.decode('utf-8').split()
    p = subprocess.run(['ld', '-shared', '-o', '/dev/null', *args], stdout=subprocess.PIPE)
    if p.returncode:
        print("python not found or not linkable, check that python3-config works")
        result.append(False)
        return False
    r = subprocess.run(['python3-config', '--extension-suffix'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()
    result.append(r)
    return r

def find_library(name, alt, *extra, pkgconfig=True, force_abi=ABIS.libcxx):
    result = libs.get(name, None)
    if result:
        return result
    if pkgconfig:
        print("Checking for", name, "via pkgconf")
        p = subprocess.run(['pkgconf', name, '--libs'], stdout=subprocess.PIPE)
        if p.returncode:
            print("Failed to find", name, "via pkgconf, looking globally")
            args = list(alt)
        else:
            args = [*p.stdout.decode('utf-8').split(), *extra]
    else:
        args = list(alt)
    p = subprocess.run(['ld', '-shared', '-o', '/dev/null', *args], stdout=subprocess.PIPE)
    if p.returncode:
        print(name, "not found")
        libs[name] = False
        return False
    libs[name] = args
    if force_abi:
        so_a_name = [i for i in args if i.endswith('.so') or i.endswith('.a') or i.startswith('-l')]
        for libname in so_a_name:
            p = subprocess.run(["ld", "-t", "-o", "/dev/null", "/dev/stdin", libname], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            lib_path = p.stdout.decode('utf-8').strip().split('\n')[1]
            with open(lib_path, 'rb') as lib:
                data = lib.read()
                if b'__11' in data and force_abi in (ABIS.libstdcpp, ABIS.C):
                    print(colorama.Fore.YELLOW, "Found", name, "but it is compiled with libc++ and you requested", force_abi, "only", colorama.Style.RESET_ALL)
                    libs[name] = False
                    return False
                if b'__cxx11' in data and force_abi in (ABIS.libcxx, ABIS.C):
                    print(colorama.Fore.YELLOW, "Found", name, "but it is compiled with libstdc++ and you requested", force_abi, "only", colorama.Style.RESET_ALL)
                    libs[name] = False
                    return False
    return args



__all__ = ["find_python", "find_library"]
