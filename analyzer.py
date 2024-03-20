import os
import platform
import subprocess


from elftools.elf.elffile import ELFFile
from git import Repo
from pyclibrary import CParser

LIBRARIES = [
    "libcrypto.so",
    "libssl.so",
]
REPOS_DIR = "repos"
REPOS = [
    ["https://github.com/WillChilds-Klein/aws-lc", "main"],
    ["https://github.com/openssl/openssl", "OpenSSL_1_0_2-stable"],
    ["https://github.com/WillChilds-Klein/ruby", "ruby_3_1"],
]


def main():
    check_dependencies()
    print("fetching sources...")
    fetch_source()
    print("building aws-lc...")
    build_awslc()
    print("building openssl...")
    build_openssl_1_0_2()
    print("scanning symbols and sources...")
    openssl_libs = get_libs(os.path.join(REPOS_DIR, "openssl"))
    awslc_libs = get_libs(os.path.join(REPOS_DIR, "aws-lc"))
    openssl_symbols = get_symbols(openssl_libs)
    awslc_symbols = get_symbols(awslc_libs)
    ruby_files = get_files(os.path.join(REPOS_DIR, "ruby"), ".h")
    ruby_files.update(get_files(os.path.join(REPOS_DIR, "ruby"), ".c"))

    ruby_openssl_symbols = set()
    valid_c_symbol_chars = set()

    def is_valid_c_symbol_char(c: str) -> bool:
        assert len(c) == 1
        return c.isalnum() or c == "_"

    for file in ruby_files:
        with open(file, "r") as f:
            contents = f.read()
            for symbol in openssl_symbols:
                idx = contents.find(symbol)
                if idx < 0:
                    continue
                if not is_valid_c_symbol_char(contents[idx + len(symbol)]) and (
                    not is_valid_c_symbol_char(contents[idx - 1]) or len == 0
                ):
                    ruby_openssl_symbols.add(symbol)
    awslc_missing = ruby_openssl_symbols.difference(awslc_symbols)
    print("parsing openssl headers...")
    print()
    # NOTE: only openssl/include/openssl took 5m28.266s
    parser = CParser(list(get_files(os.path.join(REPOS_DIR, "openssl"), ".h")))
    for s in sorted(awslc_missing, key=str.casefold):
        if s in parser.defs["functions"]:
            print(parser.defs["functions"][s])
        elif s in parser.defs["fnmacros"]:
            print(parser.defs["fnmacros"][s])
        else:
            print(f"SYMBOL NOT FOUND IN PARSER: {s} :: {parser.find(s)}")


def get_symbols(lib_paths: list[str]) -> set[str]:
    symbols = set()
    for lib_path in lib_paths:
        with open(lib_path, "rb") as f:
            elf = ELFFile(f)
            symbols.update(
                s.name
                for s in elf.get_section_by_name(".dynsym").iter_symbols()
                # filter out dynamic symbols from other linked libs (e.g. libc)
                if s.entry["st_shndx"] != "SHN_UNDEF"
            )
    return symbols


def get_libs(root: str) -> list[str]:
    return [l for l in get_files(root, ".so") if l.split(os.path.sep)[-1] in LIBRARIES]


def get_files(root: str, suffix: str = "") -> set[str]:
    files = set()
    for dpath, _, fnames in os.walk(root):
        files.update([os.path.join(dpath, fn) for fn in fnames if fn.endswith(suffix)])
    return files


def fetch_source():
    if not os.path.exists(REPOS_DIR):
        os.mkdir(REPOS_DIR)
    for url, ref in REPOS:
        path = os.path.join(REPOS_DIR, repo_from_url(url))
        if not os.path.exists(path):
            os.mkdir(path)
        repo = Repo.init(path)
        if "origin" not in repo.remotes:
            repo.create_remote("origin", url=url)
        origin = repo.remotes["origin"]
        origin.fetch()
        repo.create_head(ref, origin.refs[ref]).set_tracking_branch(
            origin.refs[ref]
        ).checkout()
        origin.pull()


def build_awslc():
    cmds = ["cmake -B build -DBUILD_SHARED_LIBS=ON", "make -C build"]
    build_common("aws-lc", cmds)


# TODO: create a Repo abc that requires users to provide a build method
def build_openssl_1_0_2():
    cmds = ["./config shared", "make"]
    build_common("openssl", cmds)


def build_common(repo: str, cmds: list[str]):
    cwd = os.path.join(REPOS_DIR, repo)
    nproc = (
        subprocess.run("nproc", stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
    )
    for cmd in cmds:
        cmd_words = cmd.split(" ")
        if cmd_words[0] == "make":
            cmd_words.extend(["-j", nproc])
        try:
            subprocess.run(
                cmd_words,
                check=True,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            print(f"WORK DIR: {cwd}")
            print(f"COMMAND: {' && '.join(cmd_words)}")
            print(f"STDERR: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            raise e


def check_dependencies():
    assert "Linux" in platform.platform(), "linux is the only supported platform"
    deps = ["make", "cmake", "nproc"]
    for dep in deps:
        subprocess.run(["which", dep], check=True, stdout=subprocess.DEVNULL)


def repo_from_url(url: str) -> str:
    return url.split("/")[-1]


if __name__ == "__main__":
    main()
