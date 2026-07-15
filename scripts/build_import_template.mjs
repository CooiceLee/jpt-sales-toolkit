import fs from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';
import { FORMAT_VERSION, businessSheets, enums, headerLabel } from './import_template/template_schema.mjs';
import { addEnumValidations, columnName, styleBusinessSheet, styleSupportSheet } from './import_template/template_style.mjs';

const outputPath = process.argv[2] || 'frontend/templates/JPT标准导入模板.xlsx';
const datasetId = process.argv[3] || randomUUID();
const workbook = Workbook.create();

const metadata = workbook.worksheets.add('说明与元数据');
metadata.getRange('A1:B13').values = [
  ['字段', '值'], ['format_version', FORMAT_VERSION], ['dataset_id', datasetId],
  ['timezone', 'Asia/Shanghai'], ['dataset_name', '请填写数据集名称'],
  ['必填业务表', '客户、商机；其余业务表按实际数据填写'],
  ['date_format', 'YYYY-MM-DD'], ['空白更新语义', '更新时空白=不修改；使用 __CLEAR__ 显式清空'],
  ['键规则', 'external key 在同一 dataset 内永久不变，禁止使用行号'],
  ['账号规则', '只填写 App 中有效 username；表格不得创建账号'],
  ['导入流程', '上传 → 预检 → 修正阻断项 → Leader 确认 → 正式导入'],
  ['颜色规则', '颜色和隐藏状态只用于来源追踪，不作为业务状态'],
  ['扩展行', '在表格末行按 Tab 或粘贴数据即可自动扩展 Excel Table'],
];
styleSupportSheet(metadata, 'A1:B13');
metadata.getRange('A1:A13').format.columnWidth = 24;
metadata.getRange('B1:B13').format.columnWidth = 70;
metadata.getRange('B2:B13').format.wrapText = true;

for (const definition of businessSheets) {
  const sheet = workbook.worksheets.add(definition.name);
  const headers = definition.columns.map(headerLabel);
  const lastCol = columnName(headers.length);
  sheet.getRange(`A4:${lastCol}5`).values = [headers, headers.map(() => null)];
  styleBusinessSheet(sheet, definition);
  addEnumValidations(sheet, definition, enums);
  const table = sheet.tables.add(`A4:${lastCol}5`, true, definition.table);
  table.style = 'TableStyleMedium2';
}

const members = workbook.worksheets.add('_成员目录');
members.getRange('A1:E2').values = [
  ['username', 'display_name', 'role', 'is_active', '说明'],
  ['', '', '', '', '账号在预检时匹配；请勿在表格中创建成员'],
];
styleSupportSheet(members, 'A1:E20');
members.getRange('A1:E100').format.columnWidth = 22;
members.getRange('E1:E100').format.columnWidth = 44;
members.getRange('E2:E100').format.wrapText = true;

const enumSheet = workbook.worksheets.add('_枚举字典');
const enumNames = Object.keys(enums);
const maxRows = Math.max(...Object.values(enums).map(values => values.length));
const enumMatrix = [enumNames];
for (let row = 0; row < maxRows; row += 1) {
  enumMatrix.push(enumNames.map(name => enums[name][row] ?? null));
}
enumSheet.getRangeByIndexes(0, 0, enumMatrix.length, enumNames.length).values = enumMatrix;
styleSupportSheet(enumSheet, `A1:${columnName(enumNames.length)}${enumMatrix.length}`);
enumSheet.getRange(`A1:${columnName(enumNames.length)}${enumMatrix.length}`).format.columnWidth = 20;

const trace = workbook.worksheets.add('_来源追踪');
trace.getRange('A1:L2').values = [[
  'source_record_key', 'file_hash', 'source_sheet', 'source_row', 'fill_rgb', 'hidden',
  'raw_date_text', 'target_entity_type', 'target_entity_key', 'match_method', 'confidence', 'raw_note',
], Array(12).fill(null)];
styleSupportSheet(trace, 'A1:L20');
trace.getRange('A1:L100').format.columnWidth = 20;

const validation = workbook.worksheets.add('_校验结果');
validation.getRange('A1:J2').values = [[
  'severity', 'sheet', 'row', 'entity_key', 'code', 'field',
  'original_value', 'suggestion', 'message', 'resolution',
], Array(10).fill(null)];
styleSupportSheet(validation, 'A1:J20');
validation.getRange('A1:J100').format.columnWidth = 22;

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange(true);
  const previewRows = Math.min(used?.rowCount || 10, 15);
  const previewCols = used?.columnCount || 8;
  const previewRange = `A1:${columnName(previewCols)}${previewRows}`;
  const preview = await workbook.render({ sheetName: sheet.name, range: previewRange, scale: 1, format: 'png' });
  const safeName = sheet.name.replaceAll('/', '_');
  await fs.writeFile(`${outputPath}.${safeName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const inspect = await workbook.inspect({
  kind: 'sheet,table', maxChars: 8000, tableMaxRows: 4, tableMaxCols: 12,
});
console.log(inspect.ndjson);
console.log(JSON.stringify({ outputPath, datasetId, sheets: workbook.worksheets.items.length }));
