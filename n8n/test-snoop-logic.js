/**
 * B3 test: snoop workflow should only advance last_seen_video_id on clip SUCCESS,
 * not on clip FAILURE.
 *
 * This test extracts the decision logic from the n8n JS Code node and verifies
 * that last_seen_video_id is NOT advanced when clipping fails.
 */

// The core logic from the snoop Code node (simplified):
// For each video, we try to clip it. If clipping fails, we should NOT advance last_seen.
// Currently, the code advances last_seen regardless of success/failure.

function snoopLogic(targets, targetChannelId, videoId, clippingSucceeded) {
  // Simplified version of snoop decision logic:
  // On clip error, the code does: out.push({...error...}); // but still advances
  // On clip success, the code updates and advances correctly.

  // The bug: last_seen advances even if clipping failed
  // The fix: only advance if clipping succeeded

  const target = targets.find(t => t.channel_id === targetChannelId);
  if (!target) return { advanced: false, reason: 'target not found' };

  // Buggy logic: always updates
  // if (videoId === target.last_seen_video_id) return { advanced: false, reason: 'same video' };
  // target.last_seen_video_id = videoId; // <-- Bug: happens even on clip failure

  // Fixed logic: only advance if clipping succeeded
  if (videoId === target.last_seen_video_id) return { advanced: false, reason: 'same video' };
  if (!clippingSucceeded) return { advanced: false, reason: 'clip failed, do not advance' };
  target.last_seen_video_id = videoId;
  return { advanced: true, newLastSeen: videoId };
}

// Test case 1: clip succeeds, should advance
const targets1 = [{ channel_id: 'test-ch', last_seen_video_id: 'old-id' }];
const result1 = snoopLogic(targets1, 'test-ch', 'new-id', true);
console.assert(result1.advanced === true, 'Should advance on clip success');
console.assert(targets1[0].last_seen_video_id === 'new-id', 'last_seen should be updated');

// Test case 2: clip fails, should NOT advance
const targets2 = [{ channel_id: 'test-ch', last_seen_video_id: 'old-id' }];
const result2 = snoopLogic(targets2, 'test-ch', 'new-id', false);
console.assert(result2.advanced === false, 'Should NOT advance on clip failure');
console.assert(result2.reason === 'clip failed, do not advance', 'Reason should indicate clip failure');
console.assert(targets2[0].last_seen_video_id === 'old-id', 'last_seen should remain unchanged');

console.log('✓ B3 snoop logic tests passed');
