# Windows / macOS 成员安装指南

## 安装前准备

向 Leader 获取与你电脑架构对应的内部测试安装包：

- Windows 10/11 x64：`Windows-x64-...-Setup.exe`
- Apple Silicon Mac：`macOS-AppleSilicon-arm64-...dmg`
- Intel Mac：`macOS-Intel-x86_64-...dmg`

当前产物明确标记 `UNSIGNED-INTERNAL`，只用于团队内部试运行。Windows SmartScreen 或 macOS Gatekeeper 可能要求手动确认；正式无阻碍分发仍需公司代码签名证书和 Apple Developer ID/notarization。

## 安装与激活

1. 安装并启动 JPT Sales Toolkit。
2. 已有团队成员选择“Join an Existing Team”。
3. 下载 `.jptreq`，发送给 Leader。
4. 收到 `.jptauth` 后，同时从另一条可信渠道取得 16 位 Leader verification code。
5. 导入 `.jptauth`、输入验证码并设置至少 8 位的本地登录密码。
6. 使用页面自动填入的成员用户名登录。

文件或验证码错误、设备不匹配、授权被篡改或已经到期时，激活会整体失败，不会留下部分账号或半授权数据。

## 本地数据位置

- Windows：`%LOCALAPPDATA%\JPT Sales Toolkit\data`
- macOS：`~/Library/Application Support/JPT Sales Toolkit/data`

覆盖升级前先从左下角用户菜单选择 `Exit JPT`，确认后台程序已经退出，再运行新安装包或替换 `.app`。升级只替换程序，不覆盖该目录；卸载默认保留业务数据、附件、备份和授权。删除本地数据必须另行人工确认。

## 无网络行为

登录、设备授权、客户和销售漏斗等核心功能可离线启动。地图 JavaScript 已随程序打包，但在线底图、地址解析和地图瓦片仍需要网络；无网时地图区域可能没有底图，不影响其他模块。
