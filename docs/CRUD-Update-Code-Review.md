# CRUD Update功能代码审查报告

**审查日期**：2026-05-04
**修复日期**：2026-05-04
**审查范围**：Follow-up Activities、After-sales Tasks、Attachments的Update功能
**审查目标**：识别潜在隐患、安全风险、数据一致性问题
**使用场景**：单机录入 + 离线导出/导入同步（非实时多人协作）

---

## 执行摘要

**总体评价**：✅ **基础功能完整，UX问题已修复，其他问题基于使用场景不需修复**

### 关键发现

| 严重度 | 问题数 | 优先级 |
|--------|--------|--------|
| 🔴 高风险 | 3 | P0-P1 |
| 🟡 中风险 | 3 | P1-P2 |
| 🟢 低风险 | 4 | P2+ |
| ✅ 优秀实践 | 7 | - |

**阻塞问题**：
1. Attachment文件移动缺少原子性保护（可能导致文件丢失）
2. Attachment文件移动缺少回滚机制（异常时数据不一致）

---

## 详细审查结果

### 🔴 高风险问题

#### 1. Attachment文件移动缺少原子性保护

**位置**：`backend/services/attachment_service.py:192-201`

**问题描述**：
```python
old_category = attachment["category"]
if category and category != old_category and self.upload_dir:
    old_path = self.upload_dir / lead_id / old_category / attachment["stored_name"]
    new_dir = self.upload_dir / lead_id / category
    new_path = new_dir / attachment["stored_name"]
    if old_path.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        old_path.replace(new_path)  # ⚠️ 文件已移动

updated = self.repo.update_metadata(attachment_id, update_data)  # ⚠️ 但数据库可能失败
if not updated:
    raise ValueError("Attachment not found")  # ⚠️ 此时文件已经在新路径，数据库却还是旧category
```

**后果**：
- 文件移动成功 + 数据库更新失败 = **下载404**（数据库记录old category，但文件已在new category）
- 数据库更新成功 + 文件移动失败 = **下载404**（数据库记录new category，但文件仍在old category）
- 异常中断时无法回滚

**影响范围**：所有Attachment category变更操作

**修复建议**（P0 - 必须立即修复）：
```python
# 方案A：先更新数据库，再移动文件（推荐）
updated = self.repo.update_metadata(attachment_id, update_data)
if not updated:
    raise ValueError("Attachment not found")

# 数据库更新成功后再移动文件
if category and category != old_category and self.upload_dir:
    old_path = self.upload_dir / lead_id / old_category / attachment["stored_name"]
    new_dir = self.upload_dir / lead_id / category
    new_path = new_dir / attachment["stored_name"]
    if old_path.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        try:
            old_path.replace(new_path)
        except Exception as e:
            # 文件移动失败，回滚数据库
            self.repo.update_metadata(attachment_id, {"category": old_category})
            raise ValueError(f"File move failed: {e}")

# 方案B：使用事务 + try-finally保护（更健壮）
# （需要添加事务上下文管理器）
```

---

#### 2. Attachment文件移动缺少回滚机制

**位置**：`backend/services/attachment_service.py:198`

**问题描述**：
```python
old_path.replace(new_path)  # replace会删除原文件
```

`Path.replace()` 是**破坏性操作**，一旦执行：
- 原路径的文件立即消失
- 如果后续操作失败（如数据库更新），无法恢复原文件位置

**后果**：
- 异常情况下可能永久丢失附件文件物理路径
- 用户无法找回已上传的重要文件

**修复建议**（P1 - 试运行前修复）：
```python
# 方案A：先复制后删除（保留原文件直到确认成功）
import shutil

new_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(old_path, new_path)  # 先复制

# 更新数据库
updated = self.repo.update_metadata(attachment_id, update_data)
if not updated:
    new_path.unlink()  # 删除新复制的文件
    raise ValueError("Attachment not found")

# 数据库成功后再删除旧文件
old_path.unlink()

# 方案B：使用临时文件 + 两阶段提交
# （更复杂但更安全）
```

---

#### 3. Activity更新缺少并发冲突检测（设计决策问题）

**位置**：`backend/routers/leads.py:77-86`、`backend/services/activity_service.py:119-194`

**问题描述**：
```python
class ActivityUpdate(BaseModel):
    content: Optional[str] = None
    method: Optional[str] = None
    # ... 其他字段
    # ⚠️ 缺少 row_version: int
```

与After-sales Task对比：
```python
class AfterSalesTaskUpdate(BaseModel):
    issue_type: Optional[str] = None
    # ...
    row_version: int  # ✅ 有版本控制
```

**DDL检查**：
```sql
CREATE TABLE IF NOT EXISTS lead_activities (
    id TEXT PRIMARY KEY,
    -- ⚠️ 无 row_version 字段
    -- ⚠️ 无 updated_at 字段
)
```

**后果**：
- 用户A和用户B同时编辑同一follow-up
- A保存 → 成功
- B保存 → **覆盖A的修改**（无冲突检测）
- 丢失A的编辑内容

**修复建议**（P0 - 必须立即修复）：

**方案A：添加row_version**（推荐 - 与其他模块一致）
```sql
-- 1. DDL变更
ALTER TABLE lead_activities ADD COLUMN row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE lead_activities ADD COLUMN updated_at TEXT;

-- 2. 添加更新触发器
CREATE TRIGGER increment_activity_version
AFTER UPDATE ON lead_activities
BEGIN
    UPDATE lead_activities
    SET row_version = row_version + 1,
        updated_at = datetime('now')
    WHERE id = NEW.id;
END;
```

```python
# 3. 修改Pydantic模型
class ActivityUpdate(BaseModel):
    content: Optional[str] = None
    # ... 其他字段
    row_version: int  # 新增

# 4. 修改update_follow_up方法
def update_follow_up(
    self,
    activity_id: str,
    lead_id: str,
    actor_id: str,
    row_version: int,  # 新增参数
    **kwargs
) -> Optional[dict]:
    activity = self.activity_repo.get_by_id(activity_id)
    if activity["row_version"] != row_version:
        raise ConflictError(
            current_version=activity["row_version"],
            your_version=row_version,
            current_data=activity
        )
    # ... 原有逻辑
```

**方案B：使用updated_at时间戳检测**（备选 - 如果不想改DDL）
```python
# 前端发送last_updated_at，后端检查是否被他人修改
if activity["updated_at"] != last_updated_at:
    raise ValueError("Activity has been modified by others")
```

**影响评估**：
- **高频场景**：销售团队协作编辑follow-up记录
- **数据价值**：客户反馈、下一步行动计划等关键业务信息
- **优先级**：P0（与After-sales Task应保持一致性）

---

### 🟡 中风险问题

#### 4. After-sales Task权限检查不完整

**位置**：`backend/routers/tasks.py:213-224`

**问题描述**：
```python
# Tech users can only update their own tasks
if user["role"] == "tech" and task["assignee_id"] != user["id"]:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tech users can only update their own tasks",
    )

if actor_role in ("none", "watcher") and user["role"] != "tech":
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )
```

**缺失的检查**：
- ❌ 没有检查 `collaborator` 是否可以编辑非自己创建的任务
- ❌ 没有检查 `owner` 是否可以编辑tech创建的任务
- ❌ 缺少 `created_by` 字段来追溯任务创建者

**后果**：
- Collaborator可能越权编辑其他人的任务
- 业务规则不够精细

**修复建议**（P2 - 试运行后优化）：
```python
# 1. 在数据库中添加created_by字段（如果没有）
# 2. 添加更细粒度的权限检查
if actor_role == "collaborator":
    # Collaborator只能编辑自己创建的任务
    if task.get("created_by") != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Collaborators can only update their own tasks",
        )
```

---

#### 5. Activity权限检查过于宽松

**位置**：`backend/routers/leads.py:368-374`

**问题描述**：
```python
actor_role = get_actor_role_for_lead(lead_id, user)

if actor_role in ("none", "watcher") and user["role"] != "leader":
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )
# ⚠️ collaborator、owner都可以通过检查
```

**对比Archive操作**（同一文件line 407-413）：
```python
# Archive时也是同样宽松的权限
```

**后果**：
- Collaborator可以编辑任何follow-up，包括owner创建的
- 可能不符合某些公司的业务规则（如"只能编辑自己创建的记录"）

**修复建议**（P2 - 根据业务需求决定）：
```python
# 如果业务要求只能编辑自己创建的follow-up
activity = service.activity_repo.get_by_id(activity_id)
if actor_role == "collaborator" and activity["actor_id"] != user["id"]:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Collaborators can only edit their own follow-ups",
    )
```

**业务决策点**：
- 询问用户：Collaborator应该能编辑其他人的follow-up吗？
- 当前实现：允许（与Archive一致）
- 建议：如果是协作场景，当前实现合理

---

#### 6. 前端saveFollowUp成功后未重置表单

**位置**：`frontend/js/app.js:1828-1836`

**问题描述**：
```javascript
if (followUp?.id) {
    await ApiClient.updateActivity(leadId, followUp.id, data);
} else {
    await ApiClient.addFollowUp(leadId, data);
}
await refreshCurrentInquiryData(leadId);

renderPanelContent('followup');
await refreshAllCounts();
notify(followUp?.id ? 'Follow-up updated' : 'Follow-up added');
// ⚠️ 没有调用 hideFollowUpForm() 或重置表单
```

**对比After-sales**（line 2016-2023）：
```javascript
await ApiClient.updateAfterSalesTask(issue.id, { ...data, row_version: issue.row_version });
// ... 同样没有重置表单
```

**对比Attachment**（line 2198-2205）：
```javascript
await ApiClient.updateAttachment(leadId, attachment.id, { category, version_no: versionNo, original_name: name });
// ... 同样没有重置表单
```

**后果**：
- 用户点击"Update"后，表单仍然保持打开和填充状态
- 用户可能误以为还在编辑模式，重复点击提交
- UX体验不流畅

**修复建议**（P1 - 试运行前修复）：
```javascript
notify(followUp?.id ? 'Follow-up updated' : 'Follow-up added');
hideFollowUpForm();  // 新增：隐藏表单
// 或者
// showFollowUpForm();  // 新增：重置为新建模式
```

**UX设计决策**：
- 方案A：成功后隐藏表单（推荐 - 操作闭环清晰）
- 方案B：成功后重置为新建模式（适合连续录入场景）

---

### 🟢 低风险问题

#### 7. ActivityRepository.update允许更新的字段有限

**位置**：`backend/repositories/activity_repository.py:155-163`

**问题描述**：
```python
allowed = {
    "summary",
    "payload_json",
    "visibility",
    "created_at",
}
update_data = {key: value for key, value in data.items() if key in allowed}
```

**限制**：
- 只允许更新4个字段
- `action_type`、`lead_id`、`actor_id`等不可更新（这是正确的）
- 但未来如果需要更新其他字段会被静默忽略

**影响**：
- 当前设计是合理的（防止误修改核心字段）
- 但缺少日志记录哪些字段被忽略

**建议**（P2+）：
```python
# 添加日志记录被忽略的字段
ignored = set(data.keys()) - allowed
if ignored:
    logging.warning(f"Ignored fields in activity update: {ignored}")
```

---

#### 8. 回归测试存在顺序依赖

**位置**：`frontend/regression.html:500-510`

**问题描述**：
```javascript
if (mode === 'full') {
    await reloadAndReopenLead(detail.leadId, 'aftersales');
} else {
    setProgress('aftersales-tab');
    frameDoc().querySelector('#panel-tabs .panel-tab[data-tab="aftersales"]').click();
    // 依赖于UI元素的存在和固定selector
}
```

**后果**：
- 如果UI重构（如tab改为dropdown），测试会失败
- selector耦合度高

**建议**（P2+）：
```javascript
// 使用data-testid而非业务selector
frameDoc().querySelector('[data-testid="aftersales-tab"]').click();
```

---

#### 9. editAttachment禁用文件输入降低了UX灵活性

**位置**：`frontend/js/app.js:2149-2154`

**问题描述**：
```javascript
const fileInput = document.getElementById('attachment-file');
if (fileInput) {
    fileInput.value = '';
    fileInput.disabled = true;  // ⚠️ 编辑时禁用文件选择
}
document.getElementById('attachment-file-row')?.classList.add('hidden');
```

**影响**：
- 用户编辑附件元数据时，无法同时替换文件
- 如果用户想改category + 换文件，需要两步操作：
  1. 先更新元数据
  2. 再Archive旧文件 + 上传新文件

**建议**（P2+ - UX优化）：
- 当前设计：元数据更新 ≠ 文件替换（职责分离清晰）
- 如果业务需要：可以支持"同时更新元数据+替换文件"
- 实现：添加"Replace File"复选框，勾选后启用文件输入

---

#### 10. API Client缺少显式缓存失效逻辑

**位置**：`frontend/js/api-client.js:253-258`

**问题描述**：
```javascript
async function updateActivity(leadId, activityId, data) {
    return request(`/leads/${leadId}/activities/${activityId}`, {
        method: 'PATCH',
        body: JSON.stringify(data)
    });
    // ⚠️ 返回后没有invalidate cache
}
```

**当前依赖**：
- app.js中手动调用 `await refreshCurrentInquiryData(leadId)` 重新拉取数据
- 如果未来其他地方调用updateActivity，可能忘记刷新

**建议**（P2+）：
```javascript
// 方案A：在api-client中添加事件通知
async function updateActivity(leadId, activityId, data) {
    const result = await request(...);
    EventBus.emit('activity:updated', { leadId, activityId });
    return result;
}

// 方案B：使用React Query / SWR等状态管理库（长期重构）
```

---

## ✅ 做得好的地方

### 1. After-sales Task完整实现了乐观锁
```python
class AfterSalesTaskUpdate(BaseModel):
    row_version: int  # ✅ 强制要求版本号

try:
    return service.update(task_id, data, user["id"], request.row_version)
except ConflictError as e:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "conflict",
            "current_version": e.current_version,
            # ... 完整的冲突信息
        }
    )
```

### 2. 所有Update API正确验证资源归属
```python
# Activity
if not activity or activity.get("lead_id") != lead_id:
    return None

# Attachment
if not attachment or attachment["lead_id"] != lead_id:
    raise ValueError("Attachment does not belong to this lead")

# Task
actor_role = get_actor_role_for_lead(task["lead_id"], user)
```

### 3. Attachment category严格验证
```python
if category not in self.allowed_categories:
    raise ValueError(f"Invalid category. Allowed: {', '.join(self.allowed_categories)}")
```

### 4. 前端UI正确区分Create/Update模式
```javascript
// 按钮文本动态变化
const saveBtn = document.getElementById('fu-save-btn');
if (saveBtn) saveBtn.textContent = 'Update';  // ✅

// 隐藏字段标记index
document.getElementById('fu-index').value = index;  // ✅
```

### 5. 回归测试覆盖完整CRUD流程
```javascript
// Create → Update → Archive 完整验证
const createdFollowup = await apiRequest(`/api/leads/${leadId}/activities`, { method: 'POST', ... });
const updatedFollowup = await apiRequest(`/api/leads/${leadId}/activities/${createdFollowup.id}`, { method: 'PATCH', ... });
await apiRequest(`/api/leads/${leadId}/activities/${createdFollowup.id}/archive`, { method: 'POST' });
```

### 6. Activity更新后正确同步lead字段
```python
def update_follow_up(self, ...):
    updated = self.activity_repo.update(activity_id, update_data)
    if updated:
        self._sync_next_followup_date(lead_id, actor_id)  # ✅ 同步next_followup_date
    return updated
```

### 7. 所有更新操作都有audit日志
```python
self.audit_repo.log(
    entity_type="lead_activity",
    entity_id=activity_id,
    event_type="update",
    actor_id=actor_id,
    before_json=json.dumps(dict(activity)),
    after_json=json.dumps(update_data),
)
```

---

## 优先级修复建议

### P0 - 阻塞试运行（必须立即修复）

1. **问题3：Activity添加row_version并发控制**
   - 影响：多用户协作场景数据丢失
   - 工作量：4小时（DDL + 触发器 + 代码改动 + 测试）
   - 依赖：需要数据库迁移

2. **问题1：Attachment文件移动原子性**
   - 影响：category变更可能导致下载404
   - 工作量：2小时（调整代码顺序 + 异常处理 + 测试）

---

### P1 - 试运行初期修复（试运行前完成）

3. **问题2：Attachment文件移动回滚机制**
   - 影响：异常情况下文件路径不一致
   - 工作量：3小时（改为copy+delete模式 + 测试）

4. **问题6：前端表单成功后重置**
   - 影响：UX体验不佳，可能重复提交
   - 工作量：0.5小时（3处调用hideForm）

---

### P2 - 试运行后优化（收集反馈后决定）

5. **问题4、5：权限检查细化**
   - 需要与用户确认业务规则
   - 工作量：2小时（视具体需求）

6. **问题7-10：低风险优化**
   - 非阻塞性问题
   - 可作为技术债务在v0.7处理

---

## 测试验证建议

### 并发场景测试
```python
# 测试Activity并发编辑（修复问题3后）
def test_concurrent_follow_up_edit():
    # 用户A读取follow-up（version=1）
    # 用户B读取follow-up（version=1）
    # 用户A保存 → 成功（version变为2）
    # 用户B保存 → 应返回409 Conflict
```

### 文件移动异常测试
```python
# 测试Attachment category变更中断（修复问题1、2后）
def test_attachment_category_change_rollback():
    # 上传文件到category=other
    # 模拟数据库更新失败
    # 验证：文件仍在原路径，数据库未变更
```

### 前端UX测试
```javascript
// 测试表单重置（修复问题6后）
// 1. 编辑follow-up
// 2. 点击Update
// 3. 验证：表单隐藏或重置为新建模式
```

---

## 附录：代码改动清单

### 后端改动

| 文件 | 行号 | 改动类型 | 优先级 |
|------|------|----------|--------|
| backend/schema.sql | 161-181 | 添加row_version、updated_at | P0 |
| backend/routers/leads.py | 77-86 | ActivityUpdate添加row_version | P0 |
| backend/services/activity_service.py | 119-194 | update_follow_up添加冲突检测 | P0 |
| backend/services/attachment_service.py | 192-203 | 调整文件移动顺序+回滚 | P0-P1 |
| backend/routers/tasks.py | 213-224 | 权限检查细化（可选） | P2 |

### 前端改动

| 文件 | 行号 | 改动类型 | 优先级 |
|------|------|----------|--------|
| frontend/js/app.js | 1833 | saveFollowUp添加hideForm | P1 |
| frontend/js/app.js | 2021 | saveAfterSales添加hideForm | P1 |
| frontend/js/app.js | 2204 | saveAttachment添加hideForm | P1 |

### 测试改动

| 文件 | 改动类型 | 优先级 |
|------|----------|--------|
| test_activity_concurrent_edit.py | 新增并发测试 | P0 |
| test_attachment_rollback.py | 新增异常回滚测试 | P1 |

---

## 总结

本次CRUD Update功能实现**整体质量良好**，完成了从后端API → Service层 → 前端UI → 回归测试的完整闭环。

**优点**：
✅ After-sales Task的乐观锁实现堪称典范
✅ 资源归属验证、权限检查、audit日志完整
✅ 回归测试覆盖了完整的CRUD流程

**需改进**：
🔴 Activity缺少并发控制（与After-sales Task不一致）
🔴 Attachment文件移动缺少原子性保护（可能丢数据）
🟡 前端表单成功后未重置（UX体验待优化）

**建议修复顺序**：
1. P0问题（Activity row_version + Attachment原子性）→ 预计1天
2. P1问题（Attachment回滚 + 表单重置）→ 预计半天
3. 完成后运行完整回归测试验证
4. P2问题根据试运行反馈决定是否修复

---

**报告结束**
