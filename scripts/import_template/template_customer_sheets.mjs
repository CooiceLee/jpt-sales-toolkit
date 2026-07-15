import { col } from './template_contract.mjs';

export const customerSheets = [
  {
    name: '客户', table: 'tbl_customers', title: '客户主数据',
    description: '一名客户一行；customer_key 在同一 dataset 内永久不变。',
    columns: [
      col('action', '操作', { required: true, enum: 'actions' }),
      col('customer_key', '客户键', { required: true }),
      col('display_name', '客户名称', { required: true }),
      col('website', '网站'), col('industry', '行业'),
      col('customer_type', '客户类型', { enum: 'customerTypes' }),
      col('company_size', '公司规模'), col('language', '语言'),
      col('country', '国家/地区'), col('city', '城市'),
      col('postal_code', '邮编'), col('address', '详细地址'),
      col('company_description', '公司简介'), col('supplemental_notes', '补充说明'),
    ],
  },
  {
    name: '客户别名', table: 'tbl_customer_aliases', title: '客户别名',
    description: '一个别名一行；语义别名须经 Leader 确认。',
    columns: [
      col('action', '操作', { required: true, enum: 'actions' }),
      col('alias_key', '别名键', { required: true }),
      col('customer_key', '客户键', { required: true }),
      col('alias_name', '别名', { required: true }),
    ],
  },
  {
    name: '联系人', table: 'tbl_contacts', title: '联系人',
    description: '一名联系人一行；每个客户最多一个主联系人。',
    columns: [
      col('action', '操作', { required: true, enum: 'actions' }),
      col('contact_key', '联系人键', { required: true }),
      col('customer_key', '客户键', { required: true }),
      col('name', '姓名', { required: true }), col('position', '职位'),
      col('email', '邮箱'), col('phone', '电话'), col('whatsapp', 'WhatsApp'),
      col('is_primary', '主联系人', { enum: 'booleans' }),
    ],
  },
];
