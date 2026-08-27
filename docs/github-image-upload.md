# 上传图片到 GitHub 评论

> 目标：把一张本地图片变成可以在 Issue / PR / 评论 markdown 里渲染的
> `![img](url)` 链接。全部方案均经本仓库实测。

## 方案总览

| 方案 | 官方 API | 匿名可访问 | 依赖 | 适用 |
|---|---|---|---|---|
| **release assets（固定预发布）** | ✅ | ✅ | 仅 `gh`/token | 推荐：CI、脚本、手动 |
| gh-imgup 扩展 | ✅ | ✅ | `gh` 扩展 | 交互式 CLI |
| gist | ✅ | ✅ | 仅 `gh` | 一次性临时图 |
| 网页拖拽（user-attachments） | ❌ 无 REST 端点 | ✅ | 浏览器 | 纯手动 |

## 方案一：release assets（推荐）

### 为什么用固定预发布

- 上传到仓库**固定 tag 的 published 预发布**（如 `_gh-imgup`），所有图复用同一条，
  Releases 列表不会越积越多
- **必须 published**，不能用 draft：draft 资产的下载 URL 对外（甚至带 token）都返回
  404，评论里会裂图（本仓库实测）

### 步骤

```bash
# 0. 鉴权：本地 gh auth login；CI 用 $GITHUB_TOKEN
REPO=14790897/MiQi
TOKEN=$(gh auth token)

# 1. 复用或创建固定预发布（存在则跳过创建）
if ! gh api "repos/$REPO/releases/tags/_gh-imgup" --jq '.id' 2>/dev/null; then
  gh api "repos/$REPO/releases" -X POST \
    -F tag_name='_gh-imgup' -F name='_gh-imgup' -F prerelease=true \
    -f body='Image assets - do not delete' --jq '.id'
fi

# 2. 上传图片（文件名加内容 hash 去重）
IMG=./screenshot.png
HASH=$(sha256sum "$IMG" | cut -c1-8)          # macOS: shasum -a 256
NAME="shot-${HASH}.png"
RID=$(gh api "repos/$REPO/releases/tags/_gh-imgup" --jq '.id')
UPLOAD_URL=$(gh api "repos/$REPO/releases/$RID" --jq '.upload_url' | sed 's/{?name,label}//')

curl -s -X POST "$UPLOAD_URL?name=$NAME" \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @"$IMG" \
  | python -c "import json,sys; print(json.load(sys.stdin)['browser_download_url'])"

# 3. 拿到的 browser_download_url 形如
#   https://github.com/OWNER/REPO/releases/download/_gh-imgup/shot-abc12345.png
```

### 贴到评论

```bash
URL="https://github.com/OWNER/REPO/releases/download/_gh-imgup/shot-abc12345.png"
gh api "repos/$REPO/issues/$PR_NUMBER/comments" \
  -F body="![screenshot]($URL)"
```

### Windows Git Bash 的坑

`sha256sum "$IMG"` 在中文/非 ASCII 文件名下会被转成八进制转义 → hash 为空 →
资产名乱码。**脚本里改用进程内 hash**（Node `createHash('sha256')` /
Python `hashlib`），不要走 shell 子进程。

## 方案二：gh-imgup 扩展

```bash
gh extension install freeasinbird/gh-imgup
gh imgup ./screenshot.png --repo OWNER/REPO   # 输出可直接粘贴的 markdown
```

底层同样是 release assets + 固定 `_gh-imgup` 预发布，封装了去重与复用。

## 方案三：gist（一次性临时图）

```bash
gh gist create ./screenshot.png --public -d "temp image"
# 取 raw URL：https://gist.githubusercontent.com/<user>/<gist-id>/raw/screenshot.png
```

适合临时分享，不适合长期归档（gist 无归属、无版本、易被清理）。

## 方案四：网页拖拽（user-attachments）

在 GitHub 网页评论框直接拖入图片，生成
`https://github.com/user-attachments/assets/<uuid>` 链接。

**此通道无公开 REST API**——自动化只能驱动真实浏览器模拟拖拽。历史上
`actions-cool/issues-helper` 等工具因此被 GitHub 按 TOS 封禁，CI 不要走这条。

## 清理与注意

- 预发布 `_gh-imgup` **不要删除**——历史评论里的图片会全部裂掉
- 公开仓库的 release asset 任何人可访问；私有仓库仅成员可见
- 同名（内容相同）重复上传会 422，脚本应复用已有资产而非报错

## 相关实现

- e2e 贴图 helper：[tests/e2e/helpers/pr-image-post.ts](../apps/desktop/tests/e2e/helpers/pr-image-post.ts)
- 技能 reference：[skills/github-workflow/references/e2e-pr-image-posting.md](../skills/github-workflow/references/e2e-pr-image-posting.md)
