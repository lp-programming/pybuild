from ._target import colorama, target
import subprocess
import enum
libs = {}

class ABIS(enum.Enum):
    libcxx = 1
    libstdcpp = 2
    C = 3

def find_python(result = [], mode="debug"):
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

def check_abi(libname):
    p = subprocess.run(["ld", "-t", "-o", "/dev/null", "/dev/stdin", libname], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    if not p.returncode:
        paths = p.stdout.decode('utf-8').strip().split('\n')[1:]
        if paths:
            lib_path = paths[0]
            with open(lib_path, 'rb') as lib:
                data = lib.read()
                if b'__11' in data:
                    return ABIS.libcxx, lib_path.endswith(".a")
                if b'__cxx11' in data:
                    return ABIS.libstdcpp, lib_path.endswith(".a")
                return ABIS.C, lib_path.endswith(".a")
    return ABIS.C, True

def find_library(name, alt, *extra, pkgconfig=True, force_abi=ABIS.libcxx, mode="debug"):
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
            a = check_abi(libname)[0]
            match a:
                case ABIS.C:
                    continue
                case ABIS.libstdcpp:
                    if force_abi in (ABIS.libcxx, ABIS.C):
                        print(colorama.Fore.YELLOW, "Found", name, "but it is compiled with libstdcpp++ and you requested", force_abi, "only", colorama.Style.RESET_ALL)
                        libs[name] = False
                        return False
                case ABIS.libcxx:
                    if force_abi in (ABIS.libstdcpp, ABIS.C):
                        print(colorama.Fore.YELLOW, "Found", name, "but it is compiled with libc++ and you requested", force_abi, "only", colorama.Style.RESET_ALL)
                        libs[name] = False
                        return False
    return args



__all__ = ["find_python", "find_library"]
