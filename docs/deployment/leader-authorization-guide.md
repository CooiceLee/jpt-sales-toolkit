# Leader 账号与设备授权指南

## 当前权限口径

- 全局角色只有 `Leader / Sales / Tech`。
- 每名成员同时只保留一条有效设备授权；换机由 Leader 用新 `.jptreq` 重签，旧授权自动转为历史记录。
- 每次授权固定 90 天，不能由界面或 API 延长；到期前 30 天提醒，7 天内显示紧急提醒。
- Tech 只读取分配给自己的售前/售后任务及关联客户、Lead；报价、金额、PO、输单原因等销售敏感字段不返回。
- 离职或设备丢失不依赖即时远程停用。Leader 本机停用会阻止后续签发或数据合并，但已经离线的旧设备不会被远程擦除。

## 首位 Leader

全新安装第一次打开时选择“Set up a new team”：

1. 创建 Leader 用户名和登录密码。
2. 创建至少 12 位的签发器口令；该口令不写入数据库，也无法找回。
3. 系统在本机生成加密 Ed25519 私钥，并同时签发当前 Leader 设备的 90 天授权。
4. 立即执行一次完整备份，并把备份 ZIP 与签发器口令分开保存。

旧版本已有账号时，系统先处于 `Legacy migration mode`。现有 Leader 登录后在 Authorization Center 初始化签发器；系统会先为当前 Leader 建立设备授权，再关闭旧模式，不会留下“无授权回退登录”通道。

## 创建与签发成员

1. 在 Authorization Center 创建成员，角色只能选择 Leader、Sales 或 Tech。
2. 成员从自己的电脑导出 `.jptreq` 并发送给 Leader。
3. Leader 选择成员和请求文件，输入签发器口令，点击签发。
4. 将 `.jptauth` 文件发给成员；将页面显示的 16 位 Leader verification code 通过另一条可信渠道发送。
5. 成员导入文件、核对验证码并设置本地登录密码。

`.jptauth` 是设备和成员专属文件，不得上传 GitHub、群共享目录或公开工单。

## Excel 导入后的账号映射

- 先在 Authorization Center 创建并启用实际成员，再处理外部 XLSX；工作簿不能创建账号。
- 来源人员姓名、缩写或大小写变体由 Leader 映射到实际账号；无法唯一匹配时必须人工选择。
- 商机 owner 只能映射到 Leader 或 Sales；售前/售后任务 assignee 只能映射到 Tech。角色不符合时阻断提交。
- 映射确认后，分别使用 Sales 和 Tech 账号验证可见范围，不能只用 Leader 账号检查导入结果。
- XLSX 只负责外部数据摄取。成员终端之间的后续共享继续使用 Export / Import 生成的 JSON 数据包。

## 续期、换机与恢复

- 普通成员：重新提交新 `.jptreq`，Leader 再签一次；Leader 目录中的旧授权记录转为历史。旧离线电脑不会即时收到撤销，仍可能使用至其本地 90 天授权到期。
- Leader 正常续期：在 Issuer Security 输入签发器口令，点击“Renew This Leader Device · 90 Days”。
- Leader 到期或从备份换机：启动页使用 Leader 用户名、登录密码和签发器口令三项完成本机恢复。
- 普通成员丢失设备：Leader 停用成员或等待其换机后重签；当前离线版本不承诺即时远程撤销。

## 备份边界

完整备份现在包含数据库、附件及 `data/config/`。其中包括 JWT secret、授权时钟和加密签发私钥，应按敏感文件保管。恢复到新 Leader 电脑后仍需执行 Leader 恢复，以重新绑定该设备。
