# CRUD Update功能代码审查报告（最终版）

**审查日期**：2026-05-04
**修复日期**：2026-05-04
**状态**：✅ **已完成，可进入试运行**

---

## 使用场景确认

**实际使用模式**：
- ✅ 各Sales单机录入、编辑数据
- ✅ 通过Export/Import文件同步销售漏斗进度
- ✅ 附件文件通过IM工具（微信/钉钉）单独共享
- ✅ 轻量化、低频使用工具
- ❌ **不是**实时多人在线协作平台

**这意味着**：
- ❌ 不存在"两人同时编辑同一条记录"的场景
- ❌ 不需要实时并发冲突检测
- ✅ 更关注单机稳定性和UX体验

---

## 修复决策总结

| 问题编号 | 问题描述 | 决策 | 理由 |
|---------|---------|------|------|
| 问题1 | Attachment文件移动原子性 | ❌ **暂不修复** | 触发概率极低（很少改category），单机场景异常可手动恢复 |
| 问题2 | Attachment文件移动回滚 | ❌ **暂不修复** | 同问题1，修复成本高（5小时），性价比低 |
| 问题3 | Activity并发冲突检测 | ❌ **不需修复** | 单机场景不存在并发编辑，导出/导入是离线覆盖（符合预期） |
| 问题4 | 表单成功后未重置 | ✅ **已修复** | 成本极低（5分钟），显著提升UX体验 |

---

## 已修复问题详情

### ✅ 问题4：表单成功后未重置（已修复）

**修复内容**：
- `frontend/js/app.js:1833` - saveFollowUp添加 `hideFollowUpForm()`
- `frontend/js/app.js:2024` - saveAfterSales添加 `hideAfterSalesForm()`
- `frontend/js/app.js:2201` - saveAttachment添加 `hideAttachmentForm()`

**修复效果**：
- ✅ 用户点击"Update"或"Save"后，表单自动隐藏
- ✅ 操作闭环清晰，防止重复提交
- ✅ UX体验提升

**验证**：
```bash
✅ node --check frontend/js/app.js  # 语法检查通过
✅ 确认hideFollowUpForm、hideAfterSalesForm、hideAttachmentForm函数存在
```

---

## 暂不修复问题（基于使用场景合理性分析）

### 问题1+2：Attachment文件移动原子性/回滚

**为什么不修复**：
1. **触发概率极低**：
   - 用户上传时就选对category（quotation/report/other等）
   - 后续几乎不改category
   - 即使改，也是低频操作

2. **单机场景风险可控**：
   - 异常中断（如断电）概率低
   - 即使发生，用户可手动恢复：删除重新上传

3. **修复成本高**：
   - 需要重构文件移动逻辑（copy→delete模式）
   - 需要添加异常回滚机制
   - 预计5小时工作量

4. **临时缓解方案**（0成本）：
   - UI提示："Attachment category一旦选定，不建议修改。如需调整，请Archive旧附件后重新上传。"

**观察策略**：
- 试运行期间监控是否有用户报告"改category后下载404"
- 如果从未触发 → 永久不修复
- 如果有用户遇到 → 再评估修复优先级

---

### 问题3：Activity并发冲突检测（row_version）

**为什么不修复**：
1. **单机场景不存在并发**：
   - 一个人不会同时编辑同一条follow-up
   - 导出/导入是离线同步，最后导入的覆盖前面的（符合预期）

2. **与After-sales不一致属于架构优化**：
   - After-sales Task有row_version是因为历史原因
   - Activity没有不影响当前使用场景

3. **修复成本高且无价值**：
   - 需要DDL迁移（ALTER TABLE + 触发器）
   - 需要修改Pydantic模型、Service层、前端代码
   - 预计4小时工作量
   - 但在单机场景下**完全用不到**

**如果未来切换到多人实时协作**：
- 届时再统一添加所有模块的row_version
- 作为架构升级的一部分

---

## 导出/导入场景说明

**用户确认的使用流程**：
1. **数据同步**：Sales导出JSON → Leader导入JSON → 更新销售漏斗进度
2. **附件共享**：通过微信/钉钉等IM工具单独发送文件
3. **完整备份**：使用Admin → Backup/Restore（包含数据+文件）

**当前设计完全符合需求**：
- ✅ Export/Import只同步JSON数据（轻量、快速）
- ✅ Attachment文件通过其他渠道共享（灵活、熟悉的工作流）
- ✅ UI已有清晰提示（frontend/index.html:499）

---

## 优秀设计保持

### ✅ After-sales Task的乐观锁实现
```python
class AfterSalesTaskUpdate(BaseModel):
    row_version: int  # 强制要求版本号

except ConflictError as e:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "conflict",
            "current_version": e.current_version,
            "your_version": e.your_version,
            "current_data": e.current_data,
        }
    )
```

### ✅ 资源归属验证
```python
if attachment["lead_id"] != lead_id:
    raise ValueError("Attachment does not belong to this lead")
```

### ✅ 完整的Audit日志
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

### ✅ 回归测试覆盖CRUD全流程
```javascript
// Create → Update → Archive 完整验证
const updated = await apiRequest(`/api/leads/${leadId}/activities/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'completed' })
});
```

---

## 试运行检查清单

### 功能验证
- [ ] Follow-up：Create → Edit → Update → Archive 完整流程
- [ ] After-sales：Create → Edit → Update → Archive 完整流程
- [ ] Attachment：Upload → Edit Metadata → Archive 完整流程
- [ ] 表单成功后自动隐藏（新修复的功能）

### 数据同步验证
- [ ] Sales A录入10条follow-up → Export
- [ ] Leader导入 → 验证数据正确
- [ ] Sales B修改5条 → Export
- [ ] Leader导入 → 验证最新修改生效（覆盖旧数据）

### 边界场景验证
- [ ] 编辑follow-up时，内容为空 → 应提示错误
- [ ] 编辑attachment metadata时，category选无效值 → 应提示错误
- [ ] 网络中断时保存 → 应提示错误，数据不丢失

---

## 低风险优化项（可选，P2+）

以下问题不影响试运行，可在v0.7或用户反馈后考虑：

1. **权限检查细化**：Collaborator是否应只能编辑自己创建的记录？
   - 当前：Collaborator可编辑任何follow-up/task
   - 如果业务需要更严格权限，可添加created_by检查

2. **ActivityRepository日志**：被忽略的字段应记录warning
   - 帮助未来调试"为什么某字段没更新"

3. **回归测试解耦**：使用data-testid代替业务selector
   - 提高测试稳定性

4. **Attachment编辑灵活性**：允许"同时更新元数据+替换文件"
   - 当前：元数据编辑时禁用文件输入（职责分离清晰）
   - 如果用户需要，可添加"Replace File"选项

---

## 技术债务追踪

### 不修复的问题（记录原因）

| 问题 | 技术债务级别 | 触发条件 | 何时重新评估 |
|------|-------------|---------|-------------|
| Attachment原子性 | 低 | 频繁改category + 异常中断 | 试运行后用户反馈 |
| Activity row_version | 低 | 切换到多人实时协作 | 架构升级时统一处理 |
| 权限检查细化 | 低 | 业务规则变更 | 用户明确提出需求 |

---

## 总结

**当前状态**：✅ **可进入试运行**

**已完成**：
- ✅ CRUD功能完整（Create → Read → Update → Archive）
- ✅ UX体验优化（表单自动隐藏）
- ✅ 回归测试覆盖
- ✅ 代码质量良好（资源验证、audit日志、权限检查）

**基于使用场景的合理决策**：
- ✅ 单机场景不需要并发控制
- ✅ 低频操作不需要过度防御性编程
- ✅ 轻量化定位符合产品愿景

**建议**：
1. 进入试运行，收集真实用户反馈
2. 观察是否有人遇到"改category后下载404"
3. 验证导出/导入流程是否顺畅
4. 根据反馈决定是否修复技术债务

---

**报告结束**
