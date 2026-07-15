export const FORMAT_VERSION = 'JPT-XLSX-1.0';

export const enums = {
  actions: ['UPSERT', 'ARCHIVE', 'RESTORE', 'SKIP'],
  booleans: ['TRUE', 'FALSE'],
  customerTypes: ['End User', 'Integrator', 'OEM', 'Distributor', 'Other'],
  salesStages: ['New', 'Assigned', 'Following', 'Quoted', 'Won', 'Lost'],
  sourceChannels: ['Email', 'Website', 'Exhibition', 'LinkedIn', 'Referral', 'Other'],
  qualityGrades: ['A', 'B', 'C', 'D'], urgencies: ['High', 'Medium', 'Low'],
  currencies: ['USD', 'EUR', 'GBP', 'CNY', 'JPY', 'Other'],
  fulfillmentStatuses: ['Not Started', 'In Progress', 'Completed'],
  assignmentTypes: ['collaborator', 'watcher'],
  activityTypes: ['follow_up', 'comment'],
  visibilities: ['all', 'internal', 'owner_only'],
  activityMethods: ['Email', 'Phone', 'Meeting', 'Video Call', 'WhatsApp', 'WeChat', 'Other'],
  activityStatuses: ['pending', 'responded', 'completed', 'scheduled'],
  preSalesStatuses: ['Open', 'In Progress', 'Completed', 'Cancelled'],
  issueTypes: ['Technical', 'Quality', 'Delivery', 'Other'],
  afterSalesStatuses: ['Open', 'In Progress', 'Resolved', 'Closed'],
};

export const headerLabel = column => `${column.label}｜${column.id}`;
export const col = (id, label, options = {}) => ({ id, label, ...options });
