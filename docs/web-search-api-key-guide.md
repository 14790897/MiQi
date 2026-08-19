# MiQi 搜索 API Key 配置指南（手把手）

> 给 MiQi 配搜索 key 后，联网搜索更稳定（不再被限流）。**不配也能用**（自动退回 DuckDuckGo），配了更稳。
> 两种 key 可任选其一，或都配（都配时自动优先用 Tavily）。

---

## 方式一：配置 Tavily（推荐，免费 1000 次/月）

**Tavily 是专为 AI 设计的搜索服务**，返回结构化结果，几乎不限流。

### 第 1 步：注册账号

1. 打开浏览器访问 **https://tavily.com** （可能需要科学上网）
2. 点右上角 **Sign Up / 注册**（支持 Google 账号一键登录，或邮箱注册）
3. 注册后自动进入控制台（Dashboard）

### 第 2 步：获取 API Key

1. 控制台左侧菜单点 **API Keys**（或首页直接能看到）
2. 点 **Create API Key / 创建密钥** 按钮
3. 复制生成的密钥——格式是 **`tvly-` 开头的一串字符**（例如 `tvly-1A2B3C4D...`）
4. **注意**：密钥只显示一次，复制后妥善保存

### 第 3 步：填进 MiQi

1. 打开 MiQi，点左下角 **系统设置**
2. 左侧菜单点 **Web 搜索与网页抓取**
3. 搜索方式选 **Auto**（推荐）或 **Tavily**
4. 在 **Tavily API Key** 输入框粘贴 `tvly-...` 密钥
5. 点底部 **保存所有 Web 设置**

### 完成 ✅

搜索现在优先走 Tavily，不再被限流。1000 次/月对个人使用非常充裕。

---

## 方式二：配置 Brave（免费 2000 次/月）

### 第 1 步：注册账号

1. 访问 **https://brave.com/search/api/** （可能需要科学上网）
2. 点 **Start for Free / 免费开始**
3. 用邮箱注册（或 Google 登录）

### 第 2 步：获取 API Key

1. 登录后进入控制台 **https://api.search.brave.com/app/keys**
2. 点 **Create / 创建** 生成订阅 key
3. 复制密钥——格式是 **`BSA` 开头的一串字符**（例如 `BSA-1a2b3c...`）

### 第 3 步：填进 MiQi

1. 打开 MiQi → **系统设置** → **Web 搜索与网页抓取**
2. 搜索方式选 **Auto** 或 **Brave**
3. 在 **Brave API Key** 输入框粘贴 `BSA-...` 密钥
4. 点 **保存所有 Web 设置**

### 完成 ✅

---

## 常见问题

| 问题 | 回答 |
|---|---|
| **两个 key 都填了用哪个？** | Auto 模式下 **Tavily 优先**，Tavily 挂了自动切 Brave |
| **不配 key 能搜索吗？** | 能——自动用 DuckDuckGo（免费无 key），只是偶尔会被限流 |
| **免费额度用完怎么办？** | 自动回落到下一个可用引擎（Brave/DuckDuckGo），不影响使用 |
| **key 填错了会怎样？** | 日志提示"authentication failed"，自动降级到无 key 的 DuckDuckGo，不报错 |
| **科学上网必须吗？** | Tavily/Brave 注册时可能需要；日常搜索 DuckDuckGo 在国内也可用（不稳定） |

---

## 快速对照

| 项目 | Tavily | Brave | DuckDuckGo |
|---|---|---|---|
| 是否需要 key | ✅（免费注册） | ✅（免费注册） | ❌ 不用 |
| 免费额度 | 1000 次/月 | 2000 次/月 | 无限（但会限流） |
| 稳定性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| 推荐场景 | 默认首选 | Tavily 备用 | 无 key 兜底 |
