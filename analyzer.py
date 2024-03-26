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
    print("biulding ruby against openssl...")
    build_ruby()
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

    # TODO: get symbols from actual ruby binary
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
    ossl_include_dir = os.path.join(REPOS_DIR, "openssl", "include", "openssl")
    parser = CParser(list(get_files(ossl_include_dir, ".h")))
    parser.process_all()
    print()
    for s in sorted(awslc_missing, key=str.casefold):
        for k in parser.defs:
            if s in parser.defs[k]:
                print(s, parser.defs[k][s])
                break
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
    # TODO make install into local repo
    build_common("aws-lc", cmds)


# TODO: create a Repo abc that requires users to provide a build method
def build_openssl_1_0_2():
    ossl_dir = os.path.abspath(f"{REPOS_DIR}/openssl/install")
    cmds = [
        f"./config --prefix={ossl_dir} --openssldir={ossl_dir}/openssl shared",
        "make",
        "make install",
    ]
    build_common("openssl", cmds)


def build_ruby():
    # TODO: patch ruby to disable TTS protocol + other unwanted stuff
    ossl_dir = os.path.abspath(f"{REPOS_DIR}/openssl/install")
    cmds = [
        "./autogen.sh",
        f"""\
            ./configure --with-openssl-dir={ossl_dir} \
                        --with-openssl-lib={ossl_dir}/lib \
                        --with-openssl-include={ossl_dir}/include \
        """.strip(),
        "make",
    ]
    env = {
        "CPPFLAGS": f"-I{ossl_dir}/include",
        "LDFLAGS": f"-L{ossl_dir}/lib",
    }
    build_common("ruby", cmds, env=env)
    ossl_lib = get_files(os.path.abspath(f"{REPOS_DIR}/ruby/.ext"), "openssl.so")
    assert len(ossl_lib) == 1, ossl_lib
    ossl_lib = next(iter(ossl_lib))
    print("checking corect OpenSSL linkage...")
    p1 = subprocess.Popen(
        ["ldd", ossl_lib], cwd=f"{REPOS_DIR}/ruby", stdout=subprocess.PIPE
    )
    p2 = subprocess.check_call(
        ["grep", f"{REPOS_DIR}/openssl/install/"],
        cwd=f"{REPOS_DIR}/ruby",
        stdin=p1.stdout,
        stdout=subprocess.DEVNULL,
    )
    p1.wait()
    print("checking corect OpenSSL version...")
    p1 = subprocess.Popen(
        [
            "./ruby",
            "-I.",
            "-I.ext/x86_64-linux",
            "-I./lib",
            "-ropenssl",
            "-e",
            "'puts OpenSSL::OPENSSL_VERSION'",
        ],
        cwd=f"{REPOS_DIR}/ruby",
        stdout=subprocess.PIPE,
    )
    p2 = subprocess.check_call(
        ["cat", "-"],
        # ["grep", "OpenSSL 1.0.2"],
        cwd=f"{REPOS_DIR}/ruby",
        stdin=p1.stdout,
    )
    p1.wait()

    # validate OSSL:
    #
    #   $ ./ruby -I./ -I.ext/x86_64-linux/ -I./lib -ropenssl -e 'puts OpenSSL::OPENSSL_VERSION'
    #   OpenSSL 1.0.2v-dev  xx XXX xxxx
    #
    #   $ ldd ./.ext/x86_64-linux/openssl.so
    #   linux-vdso.so.1 (0x00007ffdf9bdc000)
    #   libssl.so.1.0.0 => /home/ubuntu/symbol_analyzer/repos/openssl/install//lib/libssl.so.1.0.0 (0x00007f680fe9a000)
    #   libcrypto.so.1.0.0 => /home/ubuntu/symbol_analyzer/repos/openssl/install//lib/libcrypto.so.1.0.0 (0x00007f680fc00000)
    #   libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f680f800000)
    #   /lib64/ld-linux-x86-64.so.2 (0x00007f680ff7a000)


def build_common(repo: str, cmds: list[str], env: dict[str, str] = None):
    subenv = dict(os.environ)
    if env:
        subenv = dict(subenv, **env)
    cwd = os.path.join(REPOS_DIR, repo)
    nproc = (
        subprocess.run("nproc", stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
    )
    for cmd in cmds:
        cmd_words = cmd.split(" ")
        if cmd_words[0] == "make" and len(cmd_words) == 1:
            cmd_words.insert(1, "-j")
            cmd_words.insert(2, nproc)
        try:
            subprocess.run(
                cmd_words,
                check=True,
                cwd=cwd,
                env=subenv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            print(f"WORK DIR: {cwd}")
            print(f"COMMAND: {' '.join(cmd_words)}")
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
