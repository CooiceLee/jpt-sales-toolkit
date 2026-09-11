/** Fetch a complete, permission-safe inquiry panel snapshot. */
(function () {
    'use strict';

    async function load(leadId) {
        const taskOnly = RoleCapabilities.isTech();
        const [lead, activities, preSalesPage, afterSalesPage, attachments] = await Promise.all([
            ApiClient.getLead(leadId),
            taskOnly ? [] : ApiClient.listActivities(leadId),
            ApiClient.listAllPreSalesTasks({ lead_id: leadId, include_archived: true }),
            ApiClient.listAllAfterSalesTasks({ lead_id: leadId }),
            taskOnly ? [] : ApiClient.listAttachments(leadId)
        ]);
        const preSalesTasks = preSalesPage.items;
        const afterSalesTasks = afterSalesPage.items;
        // Carried so the tabs can say when they are showing part of a list.
        // A panel that shows the first page as though it were all of them is
        // how a task somebody is waiting on becomes invisible.
        const tasksComplete = PagedFetch.isComplete(preSalesPage, afterSalesPage);
        const primaryContact = getLeadPrimaryContact(lead);
        return {
            id: lead.id,
            inquiry_id: lead.display_id,
            company_name: lead.customer?.display_name || '',
            contact_name: primaryContact?.name || '',
            email: primaryContact?.email || '',
            phone: primaryContact?.phone || '',
            country: lead.customer?.country || '',
            city: lead.customer?.city || '',
            stage: lead.sales_stage,
            product: lead.product_category,
            title: lead.title,
            created_at: lead.created_at,
            row_version: lead.row_version,
            follow_ups: activities.filter(item => item.action_type === 'follow_up').map(mapFollowUpActivity),
            after_sales: afterSalesTasks.map(mapAfterSalesTask),
            sample_tasks: preSalesTasks.map(task => SamplingModule.toView(task)),
            latest_follow_up: lead.latest_follow_up || null,
            latest_follow_up_at: lead.latest_follow_up_at || lead.latest_follow_up?.created_at || '',
            latest_follow_up_at_raw: lead.latest_follow_up?.occurred_at_raw || '',
            latest_follow_up_summary: lead.latest_follow_up_summary
                || lead.latest_follow_up?.content || lead.latest_follow_up?.summary || '',
            attachments,
            _lead: lead,
            _customer: lead.customer,
            _activities: activities,
            tasks_complete: tasksComplete,
            _preSalesTasks: preSalesTasks,
            _afterSalesTasks: afterSalesTasks,
            _attachments: attachments
        };
    }

    window.InquiryPanelData = { load };
})();
