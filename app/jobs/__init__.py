"""
Background job implementations.

Jobs are discrete async functions that perform one unit of work and are
called by the sync scheduler loop. Keeping them here (instead of in
sync_scheduler) makes them individually testable and easier to replay
on demand.
"""
