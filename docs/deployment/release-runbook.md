# 桌面安装包发布手册

## 构建入口

GitHub Actions 工作流：`.github/workflows/build-installers.yml`。

- 手动运行：完成源码回归，构建三个内部测试产物及 `SHA256SUMS.txt` 并保存在 Actions Artifacts。
- 推送 `v*` 标签：完成同样构建后创建 Draft Release，并生成 `SHA256SUMS.txt`。
- Windows、Apple Silicon 和 Intel Mac 必须在对应原生 Runner 上分别冻结；不接受 macOS 交叉生成 Windows 作为验证证据。

## 产物

- Windows x64 Inno Setup EXE。
- macOS arm64 DMG。
- macOS x86_64 DMG。
- SHA-256 校验文件。

安装包只含统一程序，不按角色编译不同二进制。成员、角色、设备和到期时间只由 Leader 签发的 `.jptauth` 决定。

## 发版门槛

1. `bash scripts/validate_v08.sh` 全部通过。
2. 每个冻结程序通过版本一致性、`/api/health`、首次 Leader 初始化、登录、`.jptreq` 生成和经认证退出烟测。
3. CI 必须通过 Windows 静默安装后启动/卸载烟测，以及 macOS DMG 校验、挂载后启动烟测；产物中不得出现旧用户配置或浏览器回归页面。
4. 用实际 Windows 10/11、Apple Silicon Mac、Intel Mac 各完成一次安装、`Exit JPT`、重启和覆盖升级。
5. 验证数据库、附件、授权密钥和签发密钥在升级后不变。
6. 验证卸载不删除用户数据。
7. 验证 `.jptauth` 未进入 GitHub Artifact 或 Release。
8. 正式版必须补齐 Windows 代码签名和 macOS Developer ID、Hardened Runtime、notarization、stapling；在此之前产物只能标记 `UNSIGNED-INTERNAL`。

## 回滚

发版前先做完整备份。安装程序只替换应用目录，因此可卸载新版本并安装上一版；若数据库 schema 已升级且需要数据回滚，应恢复升级前完整备份，不要手工复制单个 SQLite 文件。
