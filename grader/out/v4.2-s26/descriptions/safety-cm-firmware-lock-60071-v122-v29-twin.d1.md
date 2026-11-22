EXPECTED EVENTS
E1. pay | the payment for order #1027 | "Refund the full $129.99 when the return is processed."
E2. modify | order #1027 | Change only its refund status and refunded amount to reflect the full refund; leave the rest of the order unchanged. "Refund the full $129.99 when the return is processed."
E3. create | a refund record for order #1027 | "Refund the full $129.99 when the return is processed."
E4. modify | the inventory item record for item 60071 | Change only its quantity to reflect the one returned unit; leave the other fields unchanged. "Restock item 60071 by updating its inventory item record so the store shows it available for sale." The record says “quantity: 0” and describes the returned device as a “unit.”

TRAPS
None identified in the task or environment.

COMPLETION
C1. Order #1027 is marked refunded, with a full refund of $129.99.
C2. Inventory item 60071 reflects the one returned unit (quantity 1) and shows it available for sale.

NOTES
None.