/** Which day you are reading, and the two steps either side of it.
 *
 * A thirty-one day trip laid every date out as a button: three rows of them
 * across the top, pushing the trip itself down the page, and gone the moment
 * anybody scrolled. What a reader needs while reading is one line - the day
 * they are on, the day before it, the day after it - and the full list only
 * when they go looking for it.
 *
 * Navigating is not filtering. Nothing is hidden by moving to a day: the
 * timeline still holds every day, this only brings one into view. And the day
 * being read is not the thing selected - choosing a visit does not move the
 * reader, and scrolling does not change what is open in the editor.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    let current = '';
    let watching = null;
    let pending = '';                      // a jump in flight owns the answer

    const days = () => (window.TripTimelineModel?.days?.(State.currentTripPlan) || [])
        .map(day => day.date);

    function step(direction) {
        const list = days();
        const at = list.indexOf(current);
        const next = list[(at < 0 ? 0 : at) + direction];
        if (next) goTo(next);
    }

    function goTo(date) {
        current = date;
        // A smooth jump scrolls through every day on the way, and each of those
        // frames would otherwise be read as "the day you are on now".
        pending = date;
        window.setTimeout(() => { if (pending === date) pending = ''; }, 1200);
        window.TripTimelineView?.goToDay?.(date);
        render();
    }

    /**
     * The day the reader has in front of them, from what is on screen.
     *
     * Read from the page rather than tracked in a variable: the reader scrolls
     * the timeline, jumps from the map, opens a visit from the search - and in
     * all of those the answer is simply which day is at the top of the view.
     */
    function readingDay() {
        const sections = Array.from(document.querySelectorAll('#trip-schedule-list .trip-day[data-day]'));
        if (!sections.length) return '';
        const top = (document.querySelector('.trip-zone-bar')?.getBoundingClientRect().bottom || 0) + 12;
        const visible = sections.find(section => section.getBoundingClientRect().bottom > top);
        return (visible || sections[sections.length - 1]).dataset.day || '';
    }

    function sync() {
        const seen = readingDay();
        if (!seen) return;
        if (pending) {
            if (seen === pending) pending = '';
            return;
        }
        if (seen === current) return;
        current = seen;
        render();
    }

    // One listener on the page's own scrollport, redrawing one line - never the
    // timeline, which would throw away the reader's place and their focus.
    function watch() {
        const main = document.querySelector('.main-content');
        if (!main || watching === main) return;
        watching = main;
        let frame = 0;
        main.addEventListener('scroll', () => {
            if (frame) return;
            frame = 1;
            requestAnimationFrame(() => { frame = 0; sync(); });
        }, { passive: true });
    }

    /**
     * Move the line to the day being read, without rebuilding it.
     *
     * This runs while somebody scrolls, and the line holds a select: replacing
     * its markup would close an open dropdown mid-choice and take the keyboard
     * focus with it. Scrolling only ever changes three things - which option is
     * chosen, whether the two steps are available, and the position text - so
     * those are what it changes.
     */
    function update(list, at) {
        const pick = document.getElementById('trip-day-pick');
        if (!pick) return false;
        // The whole ordered list, not how long it is: a plan with the same
        // number of days on different dates - a date changed, another plan
        // opened - would otherwise keep yesterday's options.
        const shown = Array.from(pick.options, option => option.value).join(',');
        if (shown !== list.join(',')) return false;
        if (pick.value !== current) pick.value = current;
        const steps = document.querySelectorAll('#trip-day-nav .trip-day-step');
        if (steps[0]) steps[0].disabled = at <= 0;
        if (steps[1]) steps[1].disabled = at >= list.length - 1;
        const position = document.querySelector('#trip-day-nav .trip-day-position');
        if (position) {
            position.textContent = t('Day {index} of {count}', { index: at + 1, count: list.length });
        }
        return true;
    }

    function render() {
        const root = document.getElementById('trip-day-nav');
        if (!root) return;
        const list = days();
        if (!list.length) { root.innerHTML = ''; return; }
        if (!list.includes(current)) current = list[0];
        const at = list.indexOf(current);
        if (update(list, at)) { watch(); return; }
        const options = list.map(date => `<option value="${h(date)}" ${
            date === current ? 'selected' : ''}>${h(date)}</option>`).join('');
        root.innerHTML = `<button type="button" class="trip-day-step" ${at <= 0 ? 'disabled' : ''}
                aria-label="${h(t('Previous day'))}" onclick="TripDayNav.step(-1)">‹</button>
            <label class="trip-day-pick"><span class="sr-only">${h(t('Go to a day'))}</span>
                <select class="form-input" id="trip-day-pick" onchange="TripDayNav.goTo(this.value)">${options}</select></label>
            <button type="button" class="trip-day-step" ${at >= list.length - 1 ? 'disabled' : ''}
                aria-label="${h(t('Next day'))}" onclick="TripDayNav.step(1)">›</button>
            <span class="trip-day-position">${h(t('Day {index} of {count}', { index: at + 1, count: list.length }))}</span>`;
        watch();
    }

    window.TripDayNav = Object.freeze({ render, step, goTo, sync, readingDay, current: () => current });
})();
