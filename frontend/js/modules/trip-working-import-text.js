/** What the import panel calls things, and what it says when it is done. */
(function() {
    // The comparison has four outcomes. Named the way the reader thinks about
    // them, not the way the comparison is written.
    const STATES = Object.freeze({
        workbook_only: 'Only the workbook changed this',
        current_only: 'Only the app changed this',
        both_same: 'Both changed it the same way',
        conflict: 'Both changed it differently — choose one',
        unchanged: 'Unchanged',
    });

    const COLUMNS = Object.freeze([
        'Field', 'When exported', 'In the workbook', 'In the app now', 'What happens',
    ]);

    function status(report, tr) {
        if (!report) return '';
        if (report.status === 'completed') {
            return tr('Imported {rows} visit(s) and {fields} field(s).', {
                rows: report.committed_rows || 0, fields: report.committed_fields || 0,
            });
        }
        if (report.issues?.length) return tr('This workbook cannot be imported yet.');
        if (report.conflicts?.length) return tr('Choose what to keep for each highlighted field.');
        return tr('Ready to import.');
    }

    window.TripWorkingImportText = { STATES, COLUMNS, status };
})();
