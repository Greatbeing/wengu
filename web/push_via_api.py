# -*- coding: utf-8 -*-
"""push_via_api.py — github.com:443 被阻断时，改走 api.github.com 推送

等价于 git push：用 Git Data API 建 blob → tree → commit → 更新 ref。
认证交给 gh CLI，token 不进入本脚本。

【关键】内容一律取自 `git cat-file blob <ref>:<path>`，即**仓库内**版本，
不是工作区文件。本仓库 core.autocrlf=true，提交时会把 CRLF 归一为 LF；
若直接读工作区原始字节上传，就会把 CRLF 写进仓库 —— 已因此踩过一次，
导致 .gitignore 与 web/verify_live.py 在远端存成 CRLF（克隆后会出现幽灵改动）。

用法：
    python push_via_api.py --message "..." [--files a b c] [--base <sha>]
"""
import argparse
import base64
import json
import os
import subprocess

REPO = "Greatbeing/wengu"
ROOT = r"D:\HermesOutput\wengu"


def run(cmd, input_data=None):
    r = subprocess.run(cmd, capture_output=True, text=True, input=input_data, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("命令失败: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout


def gh(args, payload=None):
    cmd = ["gh"] + args
    if payload is not None:
        cmd += ["--input", "-"]
        return run(cmd, input_data=payload)
    return run(cmd)


def git(*args):
    return run(["git"] + list(args)).strip()


def git_bytes(*args):
    """取原始字节（不过文本层，避免换行被再处理）"""
    r = subprocess.run(["git"] + list(args), capture_output=True, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("git 失败: %s\n%s" % (" ".join(args), r.stderr.decode("utf-8", "replace")))
    return r.stdout


def api_json(*args, payload=None):
    return json.loads(gh(list(args), payload))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--base", default=None, help="父提交 sha，默认取远端 main 当前值")
    ap.add_argument("--source", default="HEAD", help="内容取自哪个 ref（默认 HEAD）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    base = a.base or api_json("api", "repos/%s/git/refs/heads/main" % REPO)["object"]["sha"]
    base_tree = api_json("api", "repos/%s/git/commits/%s" % (REPO, base))["tree"]["sha"]
    print("父提交 :", base)
    print("父树   :", base_tree)

    files = a.files
    if not files:
        files = [f for f in git("show", "--name-only", "--format=", "HEAD").split("\n") if f.strip()]
    print("文件   :", len(files))

    entries = []
    for f in files:
        path = f.replace("\\", "/")
        content = git_bytes("cat-file", "blob", "%s:%s" % (a.source, path))
        crlf = content.count(b"\r\n")
        payload = json.dumps({"content": base64.b64encode(content).decode("ascii"),
                              "encoding": "base64"})
        sha = api_json("api", "-X", "POST", "repos/%s/git/blobs" % REPO, payload=payload)["sha"]
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
        print("  %-30s %s  %6d bytes  CRLF=%d" % (path, sha[:10], len(content), crlf))

    if a.dry_run:
        print("\n--dry-run：未创建 tree/commit")
        return

    tree_sha = api_json("api", "-X", "POST", "repos/%s/git/trees" % REPO,
                        payload=json.dumps({"base_tree": base_tree, "tree": entries}))["sha"]
    print("新树   :", tree_sha)

    name = git("log", "-1", "--format=%an")
    email = git("log", "-1", "--format=%ae")
    # 注：GitHub 会把时区归一到 UTC，故无法与本地提交 sha 完全一致；
    # 这里只保证内容与父提交正确，本地/远端的分叉在能连 github.com 时用
    #   git fetch && git reset --hard origin/main
    # 一次性对齐。
    body = {
        "message": a.message,
        "tree": tree_sha,
        "parents": [base],
        "author": {"name": name, "email": email},
        "committer": {"name": name, "email": email},
    }
    new_sha = api_json("api", "-X", "POST", "repos/%s/git/commits" % REPO,
                       payload=json.dumps(body))["sha"]
    print("新提交 :", new_sha)

    api_json("api", "-X", "PATCH", "repos/%s/git/refs/heads/main" % REPO,
             payload=json.dumps({"sha": new_sha, "force": False}))
    print("\n远端 main 已更新 →", new_sha)


if __name__ == "__main__":
    main()