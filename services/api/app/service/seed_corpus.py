"""Synthetic demo corpus: six fictional tenants on clearly distinct subjects.

Written for this sample (no third-party text, nothing to license). Distinct
domains matter: retrieval is only demonstrable when one tenant's question has an
obvious right answer that another tenant's corpus could never contain. The
default seed takes the first four (12 documents + 4 metadata files).
"""

SEED_TENANTS: list[dict] = [
    {
        "tenant_id": "acme-legal",
        "display_name": "Acme Legal",
        "documents": {
            "supplier-contracts.md": (
                "# Supplier contracts\n\nEvery supplier contract must include a signed indemnity clause. "
                "Liability is capped at twelve months of fees unless gross negligence is proven. "
                "Termination for convenience requires ninety days of written notice."
            ),
            "data-retention.md": (
                "# Data retention\n\nCustomer personal data is deleted thirty days after account closure. "
                "Invoices are retained for seven years to satisfy tax audits. "
                "Access requests from data subjects are answered within one calendar month."
            ),
            "litigation-hold.txt": (
                "A litigation hold suspends every deletion schedule for the custodians named in the notice. "
                "Custodians acknowledge the hold in writing within five business days. "
                "Holds are released only by the general counsel."
            ),
        },
    },
    {
        "tenant_id": "northwind-clinic",
        "display_name": "Northwind Clinic",
        "documents": {
            "appointments.md": (
                "# Appointments\n\nPatients can book same-day appointments by phone before ten in the morning. "
                "Missed appointments without twenty-four hours notice incur a cancellation fee. "
                "Telehealth visits are available for prescription renewals."
            ),
            "vaccinations.md": (
                "# Vaccinations\n\nSeasonal flu shots are offered every October at the walk-in desk. "
                "Children follow the national immunisation schedule recorded in their health booklet. "
                "Travel vaccines need a consultation at least six weeks before departure."
            ),
            "lab-results.txt": (
                "Blood test results are released to the patient portal within three working days. "
                "Abnormal results trigger a call from the nurse on duty. "
                "Fasting is required for twelve hours before a cholesterol panel."
            ),
        },
    },
    {
        "tenant_id": "globex-robotics",
        "display_name": "Globex Robotics",
        "documents": {
            "arm-maintenance.md": (
                "# Robot arm maintenance\n\nLubricate the six joint gearboxes every five hundred operating hours. "
                "Recalibrate the end effector after any collision event. "
                "Replace the servo encoder cables when the fault log shows signal dropouts."
            ),
            "safety-cell.md": (
                "# Safety cell\n\nThe light curtain stops the arm within forty milliseconds when broken. "
                "Operators must lock out the controller before entering the cell. "
                "Emergency stop buttons are tested at the start of every shift."
            ),
            "firmware.txt": (
                "Controller firmware updates are staged on one line before the whole plant. "
                "Roll back to the previous firmware if cycle time rises by more than five percent. "
                "Keep the motion profiles backed up before flashing."
            ),
        },
    },
    {
        "tenant_id": "greenleaf-garden",
        "display_name": "Greenleaf Garden Centre",
        "documents": {
            "tomatoes.md": (
                "# Growing tomatoes\n\nWater tomato plants deeply twice a week rather than a little every day. "
                "Stake or cage the vines early so the fruit stays off the soil. "
                "Pinch out side shoots on cordon varieties to focus the plant on fruit."
            ),
            "compost.md": (
                "# Compost\n\nMix green kitchen scraps with brown leaves at roughly one to three. "
                "Turn the heap every week and keep it as damp as a wrung-out sponge. "
                "Finished compost smells earthy and crumbles in the hand."
            ),
            "pests.txt": (
                "Slugs are controlled with copper tape and evening hand picking. "
                "Aphids are washed off with a strong jet of water or eaten by ladybirds. "
                "Rotate brassicas every year to stop clubroot building up in the soil."
            ),
        },
    },
    {
        "tenant_id": "initech-finance",
        "display_name": "Initech Finance",
        "documents": {
            "expenses.md": (
                "# Expense policy\n\nMeals while travelling are reimbursed up to sixty dollars per day. "
                "Receipts are required for any single expense above twenty-five dollars. "
                "Expense reports are submitted within thirty days of the trip."
            ),
            "procurement.md": (
                "# Procurement\n\nPurchases above ten thousand dollars need three competing quotes. "
                "Software subscriptions are approved by the finance controller. "
                "Purchase orders are raised before the vendor starts work."
            ),
            "month-end.txt": (
                "Month-end close finishes on the fifth business day of the following month. "
                "Accruals are booked for any invoice not received by the cut-off. "
                "Bank reconciliations are reviewed by a second accountant."
            ),
        },
    },
    {
        "tenant_id": "stellar-observatory",
        "display_name": "Stellar Observatory",
        "documents": {
            "telescope.md": (
                "# Telescope operations\n\nCool the main mirror for one hour before observing begins. "
                "Collimate the optics after the telescope is transported. "
                "Close the dome when wind gusts exceed forty kilometres per hour."
            ),
            "observing.md": (
                "# Observing guide\n\nThe best views of Saturn's rings come near opposition. "
                "Use a narrowband filter to bring out emission nebulae from light polluted sites. "
                "Log seeing conditions on a scale of one to five for every session."
            ),
            "public-nights.txt": (
                "Public observing nights run on the first Friday of every month. "
                "Visitors are asked to use red torches to protect night vision. "
                "Sessions are cancelled when cloud cover is above seventy percent."
            ),
        },
    },
]
