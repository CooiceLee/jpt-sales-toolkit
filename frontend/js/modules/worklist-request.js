/** Which query a list on screen belongs to.
 *
 * Reading every page solves "rows went missing". It says nothing about which
 * filter the rows on screen answer. Change the owner filter while the first
 * query is still out, and the newer answer draws first while the older one
 * arrives afterwards and draws over it: the controls say one thing, the cards
 * are from another.
 *
 * One counter per list. A load takes a ticket at the start and only writes to
 * the screen - cards, count, or error - while its ticket is the current one.
 */
(function () {
    'use strict';

    const tickets = new Map();

    function begin(list) {
        const next = (tickets.get(list) || 0) + 1;
        tickets.set(list, next);
        return Object.freeze({ list, ticket: next });
    }

    function isCurrent(request) {
        return !!request && tickets.get(request.list) === request.ticket;
    }

    window.WorklistRequest = Object.freeze({ begin, isCurrent });
})();
