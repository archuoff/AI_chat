"""Document pictures: extracted at ingest, described later by a vision model, indexed as searchable chunks.

    parsers ──► catalog.sync()        store files + one row per picture (status "waiting")
                     │                 icons / banners / repeated logos -> "skipped"; unreadable formats -> "unsupported"
                     ▼
              describe.start_job()     only when a vision deployment is configured (company Azure token)
                     │
                     ▼
              catalog.index_described()  descriptions -> "image" chunks in Qdrant (searchable, cited with a thumbnail)
"""
