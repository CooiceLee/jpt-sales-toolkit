/** The three states a visit answer can be in, and when it happened. */
(function() {
    // The same escaping the visit card it is rendered into uses.
    const h = value => window.TripVisitState.escape(value);

    // A sample or a quote is either needed, not needed, or nobody has said.
    // A blank option is not the same as "no", so it is offered as its own
    // choice and read back as nothing rather than as false.
    const ANSWERS = [
        { value: '', label: 'Not answered' },
        { value: 'yes', label: 'Yes' },
        { value: 'no', label: 'No' },
    ];

    function selected(value) {
        if (value === null || value === undefined) return '';
        return value ? 'yes' : 'no';
    }

    function options(list, current) {
        return list.map(option =>
            `<option value="${option.value}"${option.value === current ? ' selected' : ''}>`
            + `${h(I18n.t(option.label))}</option>`
        ).join('');
    }

    function answer(id, value) {
        return `<select class="form-input" id="${h(id)}">`
            + `${options(ANSWERS, selected(value))}</select>`;
    }

    function read(id) {
        const value = document.getElementById(id)?.value;
        if (value === 'yes') return true;
        if (value === 'no') return false;
        return null;
    }

    function period(stop) {
        const current = stop.actual_visit_period || '';
        const list = [
            { value: '', label: 'Not answered' },
            { value: 'AM', label: 'AM' },
            { value: 'PM', label: 'PM' },
        ];
        return `<select class="form-input" id="visit-actual-period-${h(stop.id)}">`
            + `${options(list, current)}</select>`;
    }

    window.TripVisitAnswer = { answer, read, period };
})();
