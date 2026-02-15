# 开发环境代理 & SSL 配置说明

## 背景

本地开发时如果使用了 Clash / V2Ray 等代理工具（尤其是开启了"系统代理"模式），
会导致 Python 的 aiohttp 库走系统代理，产生 SSL 证书验证失败的问题：

```
SSLCertVerificationError: certificate verify failed: unable to get local issuer certificate
```

## 涉及的代码改动

以下改动是**生产安全**的，不需要在部署前还原。

### 1. aiohttp: `trust_env=False`

**文件**：
- `src/services/llm/cloud_provider.py`（5 处 `aiohttp.ClientSession`）
- `src/services/llm/local_provider.py`（3 处 `aiohttp.ClientSession`）

**作用**：防止 aiohttp 读取 macOS 系统代理设置，确保 API 请求直连。

**生产影响**：无。生产环境不应依赖系统代理访问 LLM API。

### 2. aiohttp: `ssl=_get_aiohttp_ssl_context()`

**文件**：`src/services/llm/cloud_provider.py`

**作用**：当环境变量 `DISABLE_SSL_VERIFY=true` 时，跳过 SSL 证书验证。
默认值为 `false`（正常验证），仅本地开发需要开启。

**生产影响**：无。默认不跳过 SSL 验证。

### 3. httpx: `proxy=None`

**文件**：`src/services/embedding/adapters/openai_compatible.py`

**作用**：Embedding 请求不走代理。此改动在本次之前已存在。

## 环境变量配置

### 本地开发（有代理时）

在 `.env` 中设置：

```env
DISABLE_SSL_VERIFY=true
```

### 生产部署

在 `.env` 中设置（或不设置，使用默认值）：

```env
DISABLE_SSL_VERIFY=false
```

## 关键说明

- `.env` 文件在 `.gitignore` 中，不会提交到代码仓库
- 代码层面的 `trust_env=False` 和 `ssl=_get_aiohttp_ssl_context()` 是生产安全的
- `DISABLE_SSL_VERIFY` 已有先例：`src/services/llm/providers/open_ai.py` 中 OpenAI SDK 也使用了同样的环境变量
- 如果生产环境也遇到 SSL 问题（例如企业内网证书），可以临时开启 `DISABLE_SSL_VERIFY=true`，但建议优先安装正确的 CA 证书
