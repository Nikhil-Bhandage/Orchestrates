"""Check messages and images for user_20 and user_25."""
import sys, csv
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset

dataset_dir = Path('tmp_sample_test')
index = DatasetIndex.from_dataset(dataset_dir)
store = normalize_dataset(index)

# Check user_20 messages
uid20 = 'user_20'
messages = index.messages_by_user.get(uid20, [])
print(f'Messages for user_20: {len(messages)}')
for m in messages:
    print(f'  {m["message_id"]} request={m["request_id"]} event={m.get("related_event_id","")} text={m["message_text"][:200]}')

images = index.images_by_user.get(uid20, [])
print(f'Images for user_20: {len(images)}')
for img in images:
    print(f'  {img}')

print()
uid25 = 'user_25'
messages25 = index.messages_by_user.get(uid25, [])
print(f'Messages for user_25: {len(messages25)}')
for m in messages25:
    print(f'  {m["message_id"]} request={m.get("request_id","")} event={m.get("related_event_id","")} text={m["message_text"][:200]}')

images25 = index.images_by_user.get(uid25, [])
print(f'Images for user_25: {len(images25)}')
for img in images25:
    print(f'  {img}')
    
# Check all users with amount discrepancies
print()
print('=== Expected amount analysis - OVER estimates ===')
# For requests where our amount_safe > expected amount_safe, 
# what does the difference correspond to?
over_cases = {
    'request_02': ('user_02', '2579538.40'),
    'request_03': ('user_03', '170755.81'),
    'request_04': ('user_04', '3584793.66'),
    'request_18': ('user_18', '200.19'),
    'request_20': ('user_20', '18418.52'),
    'request_22': ('user_22', '27.66'),
    'request_24': ('user_24', '1636.98'),
    'request_25': ('user_25', '2413582.88'),
}

for rid, (uid, diff) in over_cases.items():
    # Check if there are any images for this user
    images_u = index.images_by_user.get(uid, [])
    msgs_u = index.messages_by_user.get(uid, [])
    print(f'\n{rid} ({uid}): over by {diff}')
    print(f'  images: {len(images_u)}, messages: {len(msgs_u)}')
    if messages_u:
        for m in msgs_u:
            print(f'    msg: {m["message_id"]} request={m["request_id"]} event={m.get("related_event_id","")} text={m["message_text"][:120]}')
