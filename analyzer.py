import os
import subprocess


from git import Repo


REPOS_DIR = "repos"
REPOS = [
    ["https://github.com/WillChilds-Klein/aws-lc", "main"],
    ["https://github.com/openssl/openssl", "OpenSSL_1_0_2-stable"],
    ["https://github.com/WillChilds-Klein/ruby", "ruby_3_1"],
]


def main():
    check_dependencies()
    fetch_source()
    build_awslc()
    build_openssl_1_0_2()
    # print(get_files(".", ".h"))
    print(get_files("./repos/openssl", ".a"))
    print(get_files("./repos/aws-lc", ".a"))


def get_files(root: str, suffix: str) -> list[str]:
    headers = []
    for dpath, _, fnames in os.walk(root):
        headers.extend(
            [os.path.join(dpath, fn) for fn in fnames if fn.endswith(suffix)]
        )
    return headers


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
    cmds = ["cmake -B build", "make -C build"]
    build_common("aws-lc", cmds)


def build_openssl_1_0_2():
    cmds = ["./config", "make"]
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
        subprocess.run(cmd_words, check=True, cwd=cwd)


def check_dependencies():
    deps = ["make", "cmake", "nproc"]
    for dep in deps:
        subprocess.run(["which", dep], check=True)


def repo_from_url(url: str) -> str:
    return url.split("/")[-1]


if __name__ == "__main__":
    main()
