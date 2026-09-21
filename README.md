# DEEIX-Pro

基于 [DEEIX-AI/DEEIX-Chat](https://github.com/DEEIX-AI/DEEIX-Chat) 的补丁定制层，参考 CLIProxyAPI-Pro 的维护方式：只保存 patch、应用脚本和验证入口，不维护完整上游 fork。

## 配额刷新周期

订阅有效期与配额刷新独立配置：

| 配置 | 取值 | 作用 |
| --- | --- | --- |
| 订阅周期 | 月、年、永久 | 订阅到期与价格周期，保持上游行为 |
| 配额刷新周期 | 日、月 | 每天或每月重新计算可用额度 |
| 每周期额度 | 金额 | 每个刷新周期可使用的套餐额度 |

例如月订阅、按日刷新、额度 5 美元：当天用完后，次日恢复为 5 美元；当天剩余额度不累计到次日，订阅仍按月到期。

- 按日以服务器时区每天 `00:00` 为界；按月以每月 `1 日 00:00` 为界。需要北京时间时配置容器环境变量 `TZ=Asia/Shanghai`。
- 套餐新增 `quotaRefreshInterval`（`day`／`month`），数据库启动迁移为原有套餐设置默认值 `month`。旧客户端省略该字段时，保存套餐会保留原值。
- 配额按当前时间窗口中的实际付费用量计算，不靠定时清空数据库；历史账单保留，未使用额度不结转。免费模型不占套餐额度，超额余额补扣规则沿用上游。
- 请求预留和结算保留原周期快照，跨零点完成的请求仍归原周期。切换日／月时，当前窗口中的已用额度和在途预留不会凭空清零。
- 管理端可独立设置两个周期；用户端显示日／月额度、下次刷新时间，打开的页面会在周期结束后重新读取额度。下次刷新时间按浏览器本地时间显示并带时区。

此前的日订阅补丁已移除，不保留日订阅兼容逻辑。已有生成源码请重新拉取干净上游再应用新补丁；不要在旧日订阅补丁之上叠加。

## Cloudflare Tunnel

运行镜像内置官方 `cloudflare/cloudflared:latest` 的 `cloudflared`。设置运行时环境变量 `CF_TOKEN` 后，容器同时运行 DEEIX-Chat 和：

```bash
cloudflared --no-autoupdate tunnel run --token "$CF_TOKEN"
```

例如先在本机环境设置令牌，再启动镜像（其他存储、端口与应用配置沿用上游）：

```bash
docker run -d --name deeix-pro --restart unless-stopped -e CF_TOKEN ssfun/deeix-pro:v0.4.2
```

在 Cloudflare Tunnel 控制台将服务地址设置为 `http://localhost:8080`。没有设置 `CF_TOKEN` 或值为空时，只启动 DEEIX-Chat。令牌只在容器运行时传入，无需写入镜像或 Dockerfile。

容器收到停止信号时会通知两个进程退出，最多等待 5 秒；任一进程退出会清理另一个进程。隧道进程退出视为失败，由 Docker 的重启策略恢复整个容器。cloudflared 自身的临时断线重连仍由其内部处理。

## 应用补丁

基准为上游 `0.4.2`，固定提交见 [upstream.json](upstream.json)。要求 Python 3、Git；构建依赖遵循上游 README。

```bash
git clone https://github.com/DEEIX-AI/DEEIX-Chat.git .upstream/DEEIX-Chat
git -C .upstream/DEEIX-Chat checkout 08e1f8bbca29ef89b4c8002df1db8b2a3583c420
python3 scripts/apply_upstream_patches.py --check .upstream/DEEIX-Chat
python3 scripts/apply_upstream_patches.py .upstream/DEEIX-Chat
```

脚本按编号检查所有补丁，已应用的补丁会跳过，新增补丁会补齐；某个补丁上下文不匹配或内容只应用了一部分时失败退出，不强制覆盖。升级上游时先在新 checkout 中检查、应用并验证，再更新基准。不要直接改生成目录作为长期维护方案。

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

验证包括干净应用、只检查不写入、重复应用、漂移拒绝，以及计费领域、应用服务、HTTP 校验、持久化测试，API 契约一致性与前端类型检查。新增业务测试覆盖旧库迁移、日／月额度、未用额度不结转、免费模型与用户隔离、跨日幂等结算、并发预留、周期切换及夏令时。

## GitHub Actions

CI 和发布均在开始时查询上游最新正式 Release，解析标签对应的真实提交 SHA，再将同一个 SHA 传给验证和两种架构的构建。镜像标签直接使用上游 Release 标签（例如 `v0.4.2`），不使用本仓库的 Git 标签或提交号，也无需手填版本。构建时核对上游 `VERSION`，不一致或补丁不兼容则停止发布。

`upstream.json` 保留上游仓库地址和本地复现基准；Actions 使用最新正式 Release，不会自动回退到旧基准。构建上下文为生成的 `.upstream/DEEIX-Chat`。

- **Validate DEEIX-Pro**：PR、推送 `main` 或手动触发；执行补丁、计费、API 契约及类型检查，再分别在原生 amd64／arm64 runner 上构建 Docker 镜像。构建后验证 cloudflared 二进制、环境变量及容器退出行为。CI 不发布镜像，PR 不需要 Docker Hub 凭证。
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

- `patches/0001-quota-refresh.patch`：独立配额刷新周期、生成契约和 Go 回归测试。
- `patches/0002-cloudflared.patch`：cloudflared 镜像集成与双进程启动入口。
- `scripts/apply_upstream_patches.py`：可重复执行的补丁入口。
- `scripts/validate.sh`：对生成后的上游树执行验证。
- `tests/test_apply.py`：补丁应用行为验证。
- `upstream.json`：已验证的上游来源与提交。
- `.github/workflows/`：CI、复用验证及 Docker Hub 发布工作流。
- `.github/actions/prepare-upstream/`：统一上游拉取和应用补丁入口。

构建产物应保留上游的 LICENSE、NOTICE，并遵循其许可证要求。
