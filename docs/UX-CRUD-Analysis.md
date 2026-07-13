# JPT Sales Toolkit - CRUD完整性与UX审查报告

**审查日期**：2026-05-03
**审查视角**：终端用户使用角度 + 市场CRM软件最佳实践

---

## 执行摘要

**严重度评级**：🔴 **高 - 阻塞试运行**

**核心问题**：多个模块缺少**编辑（Edit）**功能，导致用户无法修正错误，只能通过"Archive + 重新创建"的低效方式处理。

**影响范围**：
- Follow-up Activities：✗ **无Edit**，只有Archive
- After-sales Tasks：✓ **有Archive**，✗ **缺Edit**
- Attachments：✗ **无Edit**（category等元数据）

**修复状态（2026-05-03）**：✅ 已完成
- Follow-up Activities：已补 `PATCH` 后端接口、前端 Edit/Update 模式、回归校验。
- After-sales Tasks：已补齐可编辑字段、前端 Edit/Update 模式、回归校验。
- Attachments：已补元数据 `PATCH`、前端 Edit/Update 模式、分类枚举对齐、回归校验。

---

## 详细审查结果

### 1. Follow-up Activities

**当前状态**（frontend/js/app.js:1607-1687）：

| 功能 | 状态 | 实现位置 |
|------|------|----------|
| Create | ✅ 有 | line 1641: `+ Add Follow-up` |
| Read | ✅ 有 | line 1617-1637: 列表渲染 |
| Update | ✅ 已补齐 | `Edit`按钮 + `ApiClient.updateActivity()` |
| Delete | ✅ 有 | line 1626: `archiveFollowUp()` |

**用户痛点**：
1. 创建follow-up时填错了日期/方法/内容，无法修改
2. 客户反馈信息需要补充，只能Archive旧记录重新创建
3. 测试数据无法编辑，只能Archive（用户报告的问题）

**市场对标**（Salesforce, HubSpot, Pipedrive）：
- ✅ 所有主流CRM都支持Activity编辑
- ✅ 通常在列表项右侧有`Edit | Delete`操作菜单

---

### 2. After-sales Tasks

**当前状态**（frontend/js/app.js:1840-1900）：

| 功能 | 状态 | 实现位置 |
|------|------|----------|
| Create | ✅ 有 | `+ Add After-sales` |
| Read | ✅ 有 | line 1850-1872: 列表渲染 |
| Update | ✅ 已补齐 | `Edit`按钮 + `ApiClient.updateAfterSalesTask()` |
| Delete | ✅ 有 | line 1859: `archiveAfterSales()` |

**用户痛点**：
1. Issue描述需要补充细节，无法编辑
2. Status状态变化（Open → In Progress → Resolved）需要重建记录
3. Solution字段后续补充无法保存

**市场对标**：
- ✅ Zendesk/Freshdesk等服务台软件都支持Ticket编辑
- ✅ Issue状态通常通过下拉菜单直接更新，不需要重建

---

### 3. Attachments

**当前状态**（frontend/js/app.js:2003-2053）：

| 功能 | 状态 | 实现位置 |
|------|------|----------|
| Create | ✅ 有 | line 2037: `+ Upload File` |
| Read | ✅ 有 | line 2014-2033: 列表渲染 |
| Update | ✅ 已补齐 | `Edit`按钮 + `ApiClient.updateAttachment()` |
| Delete | ✅ 有 | line 2023: `archiveAttachment()` |
| Download | ✅ 有 | line 2022: `downloadAttachment()` |

**用户痛点**：
1. 文件上传时选错category（如quotation误选report），无法修改
2. 文件版本号不能手动调整
3. 元数据错误只能Archive重新上传（浪费存储空间）

**市场对标**：
- ✅ Google Drive/Dropbox允许编辑文件元数据（名称、标签等）
- ✅ 主流CRM支持修改附件category、description等字段

---

### 4. 其他模块检查

#### 4.1 Lead/Inquiry基本信息
✅ **完整** - 所有tab都有Save Changes按钮

#### 4.2 Customer信息
✅ **完整** - 有Save Changes按钮

#### 4.3 Contacts
✅ **完整** - 有Add/Edit/Archive功能（用户已实现）

#### 4.4 Assignments
✅ **完整** - 有Add/Remove功能（Leader only）

---

## UX最佳实践对比

### 市场标杆CRM软件的操作模式

| 软件 | Activity编辑 | Task编辑 | 附件元数据 | 常见操作布局 |
|------|-------------|----------|------------|--------------|
| Salesforce | ✅ 有 | ✅ 有 | ✅ 有 | 列表项右侧三点菜单 |
| HubSpot | ✅ 有 | ✅ 有 | ✅ 有 | 悬浮显示Edit/Delete |
| Pipedrive | ✅ 有 | ✅ 有 | ✅ 有 | 点击项目进入编辑模式 |
| **JPT当前** | ✅ 已补齐 | ✅ 已补齐 | ✅ 已补齐 | Edit + Archive |

### 用户交互模式推荐

**模式A：内联编辑**（推荐 - 最高效）
```
[Follow-up Item]
  Email | pending | 2024-05-01
  Content: ...
  [Edit] [Archive]  ← 点击Edit后，item展开为表单
```

**模式B：模态弹窗**（备选 - 适合复杂表单）
```
[Follow-up Item] [Edit] [Archive]
  ↓ 点击Edit
[弹窗] Edit Follow-up
  Date: [____]
  Method: [____]
  ...
  [Save] [Cancel]
```

**模式C：侧边面板**（备选 - 适合大量字段）
```
[Follow-up Item] [Edit] [Archive]
  ↓ 点击Edit
右侧面板滑出，显示完整表单
```

---

## 关键发现

### 问题根因分析

1. **后端API支持度**
   - ✅ 已补 `PATCH /api/leads/{id}/activities/{activity_id}` 更新activity
   - ✅ 已补齐 `PATCH /api/after-sales-tasks/{task_id}` 的可编辑字段
   - ✅ 已补 `PATCH /api/leads/{id}/attachments/{attachment_id}` 更新attachment元数据

2. **前端缺失原因**
   - **表单复用逻辑不完整**：现有表单（line 1642-1699）只用于Create，未复用于Update
   - **UI状态管理缺失**：没有"编辑模式"状态切换
   - **操作按钮缺失**：只渲染了Archive按钮

3. **数据结构支持**
   - ✅ 有`fu-index`字段（line 1643）暗示原设计考虑过编辑功能
   - ✅ 有完整的表单字段定义

---

## 优先级分级

### P0 - 阻塞试运行（已完成）
1. **Follow-up Activities编辑**
   - 原因：用户已报告测试数据无法清理
   - 影响：所有用户每天高频使用

### P1 - 试运行初期必修（已完成）
2. **After-sales Tasks编辑**
   - 原因：Issue状态变化需要编辑，不是重建
   - 影响：售后团队工作效率

### P2 - 试运行后补充（已提前完成）
3. **Attachments元数据编辑**
   - 原因：category选错时需要修正
   - 影响：相对低频，可通过重新上传规避

---

## 推荐实施方案

### 方案：内联编辑（推荐）

**优点**：
- ✅ 最符合用户直觉（点击即编辑）
- ✅ 无需额外弹窗，减少UI层级
- ✅ 表单复用度高

**改造范围**：
1. 在每个follow-up item右侧添加`[Edit]`按钮
2. 点击Edit后：
   - 隐藏当前item的只读显示
   - 展开现有表单，填充当前数据
   - 表单底部按钮改为`[Update]` `[Cancel]`
3. Update时调用现有的`ApiClient.updateActivity()` API

**代码量估算**：
- 新增函数：`editFollowUp(index)` - 30行
- 修改`saveFollowUp()`支持更新模式 - 10行
- UI调整 - 5行

**示例代码结构**：
```javascript
window.editFollowUp = function(index) {
    const fu = State.currentInquiry.follow_ups[index];
    showFollowUpForm(); // 复用现有表单显示逻辑

    // 填充表单
    document.getElementById('fu-index').value = index;
    document.getElementById('fu-date').value = formatDatetimeLocal(fu.date);
    document.getElementById('fu-method').value = fu.method;
    // ... 其他字段

    // 改变按钮文本
    document.querySelector('#followup-form button[onclick*="save"]').textContent = 'Update';
};

// 修改saveFollowUp支持更新模式
window.saveFollowUp = async function() {
    const index = parseInt(document.getElementById('fu-index').value);
    const isUpdate = index >= 0;

    if (isUpdate) {
        // 调用更新API
        await ApiClient.updateActivity(leadId, activityId, data);
    } else {
        // 调用创建API
        await ApiClient.addFollowUp(leadId, data);
    }
};
```

---

## 后续建议

### 短期（本周内）
1. 实现Follow-up Activities编辑功能
2. 实现After-sales Tasks编辑功能

### 中期（试运行后）
3. 实现Attachments元数据编辑
4. 统一所有列表项的操作按钮布局（Edit/Archive靠右对齐）

### 长期（v1.0前）
5. 考虑添加批量操作（批量Archive）
6. 考虑添加筛选器（显示/隐藏已归档记录）
7. 考虑添加历史记录（谁在何时编辑过）

---

## 附录：后端API检查

### Activities API
```
GET    /api/leads/{id}/activities           - ✅ 有
POST   /api/leads/{id}/activities           - ✅ 有
PATCH  /api/leads/{id}/activities/{act_id}  - ✅ 有
POST   /api/leads/{id}/activities/{act_id}/archive - ✅ 有
```

### After-sales Tasks API
```
GET    /api/after-sales-tasks?lead_id={id}  - ✅ 有
POST   /api/leads/{id}/after-sales-tasks    - ✅ 有
PATCH  /api/after-sales-tasks/{task_id}     - ✅ 有
POST   /api/after-sales-tasks/{task_id}/archive - ✅ 有
```

### Attachments API
```
GET    /api/leads/{id}/attachments           - ✅ 有
POST   /api/leads/{id}/attachments           - ✅ 有
PATCH  /api/leads/{id}/attachments/{att_id}  - ✅ 有
POST   /api/leads/{id}/attachments/{att_id}/archive - ✅ 有
GET    /api/leads/{id}/attachments/{att_id}/download - ✅ 有
```

**行动项状态**：已验证并补齐UPDATE操作。

---

**报告结束**
