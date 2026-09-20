# DEEIX-Pro

基于 [DEEIX-AI/DEEIX-Chat](https://github.com/DEEIX-AI/DEEIX-Chat) 的补丁定制层，参考 CLIProxyAPI-Pro 的维护方式：只保存 patch、应用脚本和验证入口，不维护完整上游 fork。

## 日订阅周期

订阅方案新增「日」（`day`），与永久、月、年并列：

- 管理端可选择日周期并保存价格及周期额度。
- 后端接口接受 `day`，数据库读写不会把它归一化为月。
- 直接订阅和支付到账按购买的周期数计算到期时间：1 个周期为 1 日，7 个周期为 7 日；续期沿用上游权益队列。
- 用户订阅卡片、付款确认及管理端价格展示支持「金额 / 日」，含中英文文案。
- Swagger 与生成的 TypeScript API 类型同步更新。

按上游 `AddDate` 规则计算日历日，保留起始时间；本地时区遇到夏令时，一日可能为 23 或 25 小时。金额和额度仍表示每个方案周期的配置值。既有永久、月、年方案不自动转换，也不自动创建日方案。

周期字段原本为字符串，新增取值无需数据库结构迁移。日方案上线后回退到原版上游会把 `day` 识别为默认月周期，因此已有日方案的数据应继续使用支持日周期的版本。

## 应用补丁

基准为上游 `0.4.2`，固定提交见 [upstream.json](upstream.json)。要求 Python 3、Git；构建依赖遵循上游 README。

```bash
git clone https://github.com/DEEIX-AI/DEEIX-Chat.git .upstream/DEEIX-Chat
git -C .upstream/DEEIX-Chat checkout 08e1f8bbca29ef89b4c8002df1db8b2a3583c420
python3 scripts/apply_upstream_patches.py --check .upstream/DEEIX-Chat
python3 scripts/apply_upstream_patches.py .upstream/DEEIX-Chat
```

脚本重复运行会识别已应用状态；上下文不匹配或只应用了一部分时失败退出，不强制覆盖。升级上游时先在新 checkout 中检查、应用并验证，再更新基准。不要直接改生成目录作为长期维护方案。

应用后按上游方式构建，例如在本仓库根目录执行：

```bash
docker build -t deeix-pro:local .upstream/DEEIX-Chat
```

## 验证

Go 版本须满足上游 `backend/go.mod`（当前要求 1.26.8 或更新版本）；前端使用上游锁定的 pnpm 10.17.0。

```bash
(cd .upstream/DEEIX-Chat && npx --yes pnpm@10.17.0 install --frozen-lockfile)
python3 tests/test_apply.py .upstream/DEEIX-Chat
scripts/validate.sh .upstream/DEEIX-Chat
```

验证包括干净应用、只检查不写入、重复应用、漂移拒绝，以及计费领域、应用服务、HTTP 校验、持久化测试，API 契约一致性与前端类型检查。新增业务测试覆盖日周期规范化、直接订阅、支付到账、重复回调、多日、跨月跨年、闰日及夏令时，兼容原有周期。

## GitHub Actions

CI 和发布均在开始时查询上游最新正式 Release，解析标签对应的真实提交 SHA，再将同一个 SHA 传给验证和两种架构的构建。镜像标签直接使用上游 Release 标签（例如 `v0.4.2`），不使用本仓库的 Git 标签或提交号，也无需手填版本。构建时核对上游 `VERSION`，不一致或补丁不兼容则停止发布。

`upstream.json` 保留上游仓库地址和本地复现基准；Actions 使用最新正式 Release，不会自动回退到旧基准。构建上下文为生成的 `.upstream/DEEIX-Chat`。

- **Validate DEEIX-Pro**：PR、推送 `main` 或手动触发；执行补丁、计费、API 契约及类型检查，再分别在原生 amd64／arm64 runner 上构建 Docker 镜像。CI 不发布镜像，PR 不需要 Docker Hub 凭证。
- **Publish Docker Hub**：推送 `v*` 标签或手动触发；先通过同一套验证，再构建并推送两种架构，按本次构建的 digest 合并为多架构镜像。某一架构失败时不发布最终标签。

在 GitHub 仓库 **Settings → Secrets and variables → Actions** 配置：

| 类型 | 名称 | 说明 |
| --- | --- | --- |
| Secret | `DOCKERHUB_USERNAME` | Docker Hub 登录用户名 |
| Secret | `DOCKERHUB_TOKEN` | 对目标镜像仓库有写入权限的访问令牌 |
| Variable（可选） | `DOCKERHUB_IMAGE` | `命名空间/镜像名`，例如 `ssfun/deeix-pro`；默认是用户名加当前 GitHub 仓库名的小写形式 |

在 Actions 中手动运行 **Publish Docker Hub** 即可构建上游最新版。推送本仓库的 `v*` 标签仍可触发发布，但该标签仅作为触发入口，不影响镜像版本号。只有手动勾选 `publish_latest` 才额外更新 `latest`。

例如上游最新 Release 是 `v0.4.2`，发布结果就是 `ssfun/deeix-pro:v0.4.2`。同一上游版本下修改补丁并重新发布，会更新该版本标签；镜像内的 Pro 提交元数据可区分具体构建。

工作流复用上游 Dockerfile，保留 LICENSE／NOTICE；镜像元数据记录 Pro 提交和上游提交，便于追溯。依赖缓存与按架构划分的 BuildKit 缓存用于减少重复构建。两个发布任务不会并行执行，以避免同时覆盖发布标签。

## 文件

- `patches/0001-subscription-day.patch`：完整业务修改、生成契约和 Go 回归测试。
- `scripts/apply_upstream_patches.py`：可重复执行的补丁入口。
- `scripts/validate.sh`：对生成后的上游树执行验证。
- `tests/test_apply.py`：补丁应用行为验证。
- `upstream.json`：已验证的上游来源与提交。
- `.github/workflows/`：CI、复用验证及 Docker Hub 发布工作流。
- `.github/actions/prepare-upstream/`：统一上游拉取和应用补丁入口。

构建产物应保留上游的 LICENSE、NOTICE，并遵循其许可证要求。
