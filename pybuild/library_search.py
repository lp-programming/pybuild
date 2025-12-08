from ._target import colorama, target, CXX, LD, pkg
import subprocess
import enum
import shlex
import pathlib
import dataclasses
import mmap
import threading
import re
import itertools

libs = {}

try:
    subprocess.Popen("pkgconf", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pkgconf = "pkgconf"
except:
    pkgconf = "pkg-config"

class linker_dict(dict):
    def __or__(self, other):
        d = linker_dict(**self)
        for k, v in other.items():
            my_v = self.get(k, self.get('default')) | shared # it's always legal to select shared over static
            new_v = v & my_v
            d[k] = new_v
            if new_v != v:
                print("Cannot expand linker options. If you mean to override, set it up explicitly")
        return d

class LS:
    def __init__(self, *others, name=None):
        self.name = name
        if name:
            self.allowed = (self,)
        else:
            self.allowed = others
    def __hash__(self):
        if self.name:
            return hash(self.name)
        return hash(tuple(self.others))
    def __eq__(self, other):
        if other:
            return set(self.allowed) == set(other.allowed)
        return False

    def __or__(self, other):
        return LS(*self.allowed, *other.allowed)

    def __and__(self, other):
        if other is None:
            return None
        nv = []
        for i in self.allowed:
            if i in other.allowed:
                nv.append(i)
        if not nv:
            return None
        return LS(*nv)
    __rand__ = __and__

    def __repr__(self):
        if self.name:
            return self.name
        return f'({str.join(" | ", (repr(i) for i in self.allowed))})'
    def __iter__(self):
        yield from self.allowed

static = LS(name="static")
shared = LS(name="shared")

class ABIS(enum.Enum):
    libcxx = 1
    libstdcpp = 2
    C = 3

@dataclasses.dataclass(init=False)
class Library(pkg):
    found: bool
    name: str
    path: pathlib.Path
    ldflags: list
    abi: ABIS
    link_mode: LS
    license: str
    def getLDFlags(self, mode="debug"):
        if self.found:
            yield self.name
        yield from self.ldflags

    def __init__(self, library, Libs, ld_flags, abis, link_mode=None, link_mode_map=None):
        self.found = False
        self.name = library
        self.path = None
        self.ldflags = []
        self.abi = None
        if link_mode_map:
            if library.startswith('-l'):
                ln = 'lib'+library[2:]
            else:
                ln = library
            link_mode = link_mode_map.get(
                ln,
                link_mode_map.get("default", shared))
        self.link_mode = None
        self.link_mode_map = link_mode_map
        if link_mode is None:
            return
        maybe_path = pathlib.Path(library)
        if maybe_path.exists():
            abi = self.get_abi(maybe_path)
            if abi in abis:
                self.found = True
                self.name = library
                self.path = maybe_path
                self.ldflags = [*Libs, *ld_flags]
                self.abi = abi
                self.link_mode = shared if library.endswith(".so") else static
            return
        if library.startswith("-l"):
            basename = library[2:]
        else:
            basename = library
        prefixes = ["/", "/lib", "/Lib"]
        suffixes = [".o", ".a", ".so(.[0-9]+)*"]
        for suffix in suffixes:
            if basename.endswith(suffix):
                file_names_ends = [basename]
                break
        else:
            file_names_ends = [basename + "(-[0-9.]+)*" + suffix for suffix in suffixes]
        file_names = []
        for prefix in prefixes:
            for fn in file_names_ends:
                file_names.append(prefix + fn)
        for lm in link_mode:
            p = subprocess.run([CXX,
                                "-Wl,--trace", "-o", "/dev/null", "-nostdlib", "-Wl,--whole-archive",
                                f"-{lm}",
                                *Libs,
                                *ld_flags,
                                library],
                               stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            lines = {line.rsplit('(', 1)[0] : True for line in p.stdout.decode('utf-8').splitlines()}
            for line in itertools.chain(lines, self.ld_search(library, Libs, lm)):
                for file_name in file_names:
                    if re.match(file_name, "/"+line.strip().rsplit("/", 1)[1]):
                        abi = self.get_abi(line.strip())
                        if abi in abis:
                            self.found = True
                            self.path = pathlib.Path(line.strip())
                            self.ldflags = [*Libs, *ld_flags, library]
                            self.abi = abi
                            self.link_mode = lm
                            return

    def ld_search(self, library, Libs, lm):
        print(f"{CXX} failed to resolve library, using {LD}")
        p = subprocess.run([LD, f"-{lm}", "--whole-archive", "-o", "/dev/null", "-t", library, *Libs], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        yield from p.stdout.decode('utf-8').splitlines()

    _license = None
    _license_lookup = None
    @property
    def license(self):
        if self._license_lookup is not None:
            return "Pending"
        if self._license is None:
            self.guess_license()
            return "Pending"
        return self._license
    @license.setter
    def license(self, val):
        self._license = val
        self._license_lookup = None

    def guess_license(self):
        if self.path is None:
            self.license = "(unused)"
            return
        with open(self.path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                idx = mm.find(b"SPDX-License-Identifier:")
                if idx > -1:
                    f.seek(idx)
                    self.license = f.readline().decode('utf-8').split(":", 1)[1].strip()
                    return
        # No SPDX license information, fall back to async platform-specific checking
        # We lack an event loop, so we'll just have to spawn of a worker thread :(
        equery_exists = not subprocess.run(["which", "equery"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
        if equery_exists:
            def equery():
                pkg_owner = subprocess.run(["equery", "b", self.path], stdout=subprocess.PIPE)
                if not pkg_owner.returncode:
                    pkg_atom = re.split("-[0-9]", pkg_owner.stdout.decode('utf-8'))[0]
                    meta = subprocess.run(["equery", "m", pkg_atom], stdout=subprocess.PIPE)
                    if not meta.returncode:
                        metadata = meta.stdout.decode('utf-8').splitlines()
                        for line in metadata:
                            if line.startswith('License:'):
                                self.license = line.split("License:", 1)[1].strip()
                                return
                self.license = "Unknown"
            self._license_lookup = threading.Thread(target=equery)
            self._license_lookup.start()
        else:
            print("Cannot determine license due to missing equery.")
            self.license = "unknown"

    @staticmethod
    def get_abi(lib_path):
        with open(lib_path, 'rb') as lib:
            data = lib.read()
            if b'__11' in data:
                return ABIS.libcxx
            if b'__cxx11' in data:
                return ABIS.libstdcpp
        return ABIS.C

class Package(pkg):
    found: bool
    name: str
    cflags: list
    ldflags: list
    libs: list[Library]
    link_mode: LS
    link_mode_map: {str:LS}

    def validate(self, mode):
        return self.found

    def getCFlags(self, mode="debug"):
        if self.found:
            return self.cflags
        return []

    def getLDFlags(self, mode="debug", link_mode=shared):
        if self.found:
            statics = []
            seen = [*self.ldflags]
            yield from self.ldflags
            for lib in self.libs:
                if lib.found:
                    for flag in lib.getLDFlags():
                        if flag not in seen:
                            seen.append(flag)
                            if flag.startswith("-l") and shared in link_mode and lib.link_mode is static:
                                statics.append(flag)
                            else:
                                yield flag
            if statics:
                yield from [
                    "-Wl,-Bstatic",
                    *statics,
                    "-Wl,-Bdynamic"
                ]
    def __init__(self, found, name, cflags, ldflags, libraries, link_mode=shared, link_mode_map=None):
        self.found = found
        self.name = name
        self.cflags = cflags
        self.ldflags = ldflags
        self.libs = libraries
        self.link_mode = link_mode
        self.link_mode_map = link_mode_map

    @classmethod
    def find_package(cls, name, pkgconf_flags=(), abis=[ABIS.C, ABIS.libcxx], link_mode=shared, link_mode_map=None):
        """
        Find a package via pkgconf. If unsuccessful, returns a not-found package. This lets you use the package in branchless code
        """
        p = subprocess.run([pkgconf, name, "--exists", "--no-uninstalled", *pkgconf_flags], stdout=subprocess.PIPE)
        if p.returncode:
            print("pkgconf cannot find", name)
            return cls(False, name, cflags=[], ldflags=[], libraries=[], link_mode=next(iter(link_mode)))
        p = subprocess.run([pkgconf, name, "--cflags", "--keep-system-cflags", "--no-uninstalled", *pkgconf_flags], stdout=subprocess.PIPE)
        cflags = shlex.split(p.stdout.decode("utf-8"))
        for lm in link_mode:
            p = subprocess.run([pkgconf, name, f"--{lm}", "--libs-only-l", "--keep-system-libs", "--no-uninstalled", *pkgconf_flags], stdout=subprocess.PIPE)
            libs = shlex.split(p.stdout.decode('utf-8'))
            p = subprocess.run([pkgconf, name, f"--{lm}", "--libs-only-L", "--keep-system-libs", "--no-uninstalled", *pkgconf_flags], stdout=subprocess.PIPE)
            Libs = shlex.split(p.stdout.decode('utf-8'))
            p = subprocess.run([pkgconf, name, f"--{lm}", "--libs-only-other", "--keep-system-libs", "--no-uninstalled", *pkgconf_flags], stdout=subprocess.PIPE)
            ld_flags = shlex.split(p.stdout.decode('utf-8'))
            libraries = [Library(lib, Libs, ld_flags, abis, link_mode, link_mode_map) for lib in libs]
            for lib in libraries:
                if not lib.found:
                    break
            else:
                return cls(True, name, cflags, [*Libs, *ld_flags], libraries, link_mode, link_mode_map)
        print("pkgconf found", name, "but could not satisfy ABI or link-mode constraints")
        return cls(False, name, cflags=[], ldflags=[], libraries=[], link_mode=next(iter(link_mode)), link_mode_map={})

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


__all__ = ["find_python", "Package", "Library", "ABIS", "static", "shared"]


