const BRAND = '#8B1A1A';
const LIGHT = '#F4F5F7';
const BORDER = '#D7DADF';

export function styleBusinessSheet(sheet, definition, rowLimit = 50) {
  const lastCol = columnName(definition.columns.length);
  sheet.showGridLines = false;
  sheet.mergeCells(`A1:${lastCol}1`);
  sheet.getRange('A1').values = [[definition.title]];
  sheet.getRange('A1').format = {
    fill: BRAND, font: { bold: true, color: '#FFFFFF', size: 16 },
    rowHeight: 32, verticalAlignment: 'center',
  };
  sheet.mergeCells(`A2:${lastCol}2`);
  sheet.getRange('A2').values = [[definition.description]];
  sheet.getRange('A2').format = {
    fill: '#FCEEEE', font: { color: '#5C2020', italic: true },
    rowHeight: 25, verticalAlignment: 'center', wrapText: true,
  };
  sheet.getRange(`A4:${lastCol}4`).format = {
    fill: '#343A40', font: { bold: true, color: '#FFFFFF' },
    rowHeight: 34, wrapText: true, verticalAlignment: 'center',
    borders: { preset: 'outside', style: 'thin', color: BORDER },
  };
  sheet.getRange(`A5:${lastCol}${rowLimit}`).format = {
    font: { color: '#222222' }, verticalAlignment: 'top',
  };
  sheet.getRange(`A5:${lastCol}${rowLimit}`).format.rowHeight = 22;
  sheet.freezePanes.freezeRows(4);

  definition.columns.forEach((column, index) => {
    const letter = columnName(index + 1);
    const range = sheet.getRange(`${letter}5:${letter}${rowLimit}`);
    range.format.columnWidth = widthFor(column.id);
    if (column.type === 'date') range.format.numberFormat = 'yyyy-mm-dd';
    if (column.type === 'datetime') range.format.numberFormat = 'yyyy-mm-dd hh:mm';
    if (column.type === 'number') range.format.numberFormat = '#,##0.00';
    if (column.required) {
      sheet.getRange(`${letter}4`).format.fill = BRAND;
      range.conditionalFormats.add('containsBlanks', { fill: '#FFF2F2' });
    }
  });
}

export function styleSupportSheet(sheet, range = 'A1:H20') {
  const headerEnd = range.match(/:([A-Z]+)\d+$/)?.[1] ?? 'H';
  sheet.showGridLines = false;
  sheet.getRange(range).format.font = { color: '#222222' };
  sheet.getRange(`A1:${headerEnd}1`).format = {
    fill: BRAND, font: { bold: true, color: '#FFFFFF' }, rowHeight: 28,
  };
  sheet.freezePanes.freezeRows(1);
}

export function addEnumValidations(sheet, definition, enums, rowLimit = 50) {
  definition.columns.forEach((column, index) => {
    if (!column.enum) return;
    const letter = columnName(index + 1);
    sheet.getRange(`${letter}5:${letter}${rowLimit}`).dataValidation = {
      rule: { type: 'list', values: enums[column.enum] },
    };
  });
}

function widthFor(id) {
  if (id.includes('description') || id.includes('notes') || id.includes('content')) return 32;
  if (id.includes('date') || id.includes('amount') || id.includes('value')) return 16;
  if (id.includes('username') || id.includes('_key')) return 20;
  return 18;
}

export function columnName(number) {
  let name = '';
  for (let value = number; value > 0; value = Math.floor((value - 1) / 26)) {
    name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
  }
  return name;
}

export const colors = { BRAND, LIGHT, BORDER };
