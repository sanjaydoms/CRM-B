"""Post-delivery alteration domain.

An alteration is NOT a reopening of an order. Once an Order reaches
Delivered it is history: its status, stages, garment jobs, pricing, payments
and stock movements are read-only from here on. A customer who comes back
because a waist is loose starts a new, separate process that merely *points*
at the order and the garment it concerns.

Nothing in this package writes to Order, OrderStage, OrderStageHistory,
GarmentJob, ProductionTask or QCRecord, and the regression tests in
apps/alterations/test_regression.py exist to keep it that way.
"""
