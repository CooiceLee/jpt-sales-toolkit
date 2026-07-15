import { customerSheets } from './template_customer_sheets.mjs';
import { leadSheets } from './template_lead_sheets.mjs';
import { taskSheets } from './template_task_sheets.mjs';

export { FORMAT_VERSION, enums, headerLabel } from './template_contract.mjs';

export const businessSheets = [
  ...customerSheets,
  ...leadSheets,
  ...taskSheets,
];
