import { col } from './template_contract.mjs';

export const taskSheets = [
  {
    name: '售前任务', table: 'tbl_pre_sales_tasks', title: '售前任务',
    description: '多人协作时一人一行，并使用相同 task_group_key。',
    columns: [
      col('action', '操作', { required: true, enum: 'actions' }),
      col('task_key', '任务键', { required: true }),
      col('task_group_key', '任务组键'), col('lead_key', '商机键', { required: true }),
      col('assignee_username', '负责账号', { required: true }),
      col('status', '状态', { required: true, enum: 'preSalesStatuses' }),
      col('request_description', '需求描述', { required: true }),
      col('request_date', '提出日期', { type: 'date' }),
      col('due_date', '到期日期', { type: 'date' }),
      col('competitor', '竞品'), col('key_points', '关键点'), col('concerns', '顾虑'),
      col('progress_text', '进展'), col('result_summary', '结果'),
      col('next_action', '下一步行动'), col('supplemental_notes', '补充说明'),
    ],
  },
  {
    name: '售后任务', table: 'tbl_after_sales_tasks', title: '售后任务',
    description: '售后状态将同步推导商机服务状态。',
    columns: [
      col('action', '操作', { required: true, enum: 'actions' }),
      col('task_key', '任务键', { required: true }),
      col('task_group_key', '任务组键'), col('lead_key', '商机键', { required: true }),
      col('assignee_username', '负责账号', { required: true }),
      col('issue_type', '问题类型', { required: true, enum: 'issueTypes' }),
      col('status', '状态', { required: true, enum: 'afterSalesStatuses' }),
      col('issue_description', '问题描述', { required: true }),
      col('issue_date', '问题日期', { type: 'date' }),
      col('due_date', '到期日期', { type: 'date' }), col('solution', '解决方案'),
      col('customer_satisfaction', '客户满意度'),
      col('lessons_learned', '经验教训'), col('remarks', '备注'),
    ],
  },
];
