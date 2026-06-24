## 2024-06-24 - N+1 Booth Loading in Admin Room List
**Learning:** Found a severe N+1 query issue in `admin_room_list` where iterating through rooms and executing `list_booths_for_room` fired a separate DB query per room. Because SQL Alchemy's standard setup didn't transparently batch these, it linearly scales latency with room count.
**Action:** Always prefer grouped aggregation queries (`func.count` with `.group_by(room_id)`) fetched in a single lookup over looping nested dependent queries when presenting lists of entities with aggregate metrics.
