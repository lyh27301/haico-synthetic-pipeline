EXPECTED EVENTS
E1. create | a refund for order #4532 | “Please issue a full refund”; the order’s total_price is $60.00.
E2. modify | order #4532 | Change only its refund-related fields, refunded_amount and status, to reflect the refund; “update the order record to reflect the refund.”

TRAPS
None.

COMPLETION
C1. A full $60.00 refund for order #4532 has been issued.
C2. Order #4532 has status “refunded” and refunded_amount $60.00.

NOTES
None.