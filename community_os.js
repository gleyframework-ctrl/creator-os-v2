// community_os.js
function cosBuildPrompt() {
  var name = document.getElementById('cosName').value || 'My Community';
  var members = document.getElementById('cosMembers').value || 0;
  var platform = document.getElementById('cosPlatform').value;
  var struggle = document.getElementById('cosStruggle').value;
  var hours = document.getElementById('cosHours').value;
  var dna = (window.cfState && cfState.dna) || {};
  var niche = dna.niche || 'not set';
  var avatar = dna.avatar || 'not set';
  var offer = dna.offer || 'not set';

  var struggleMap = {
    low_engagement: 'low member engagement',
    no_sales: 'no sales from the community',
    no_signals: 'cannot spot buyer signals',
    too_much_work: 'too much time managing it',
    wrong_members: 'wrong members joined'
  };
  var struggleLabel = struggleMap[struggle] || struggle;

  return 'You are a Community OS Architect trained in the One Group Playbook, Community Conversion OS, Buyer Signal Cheat Sheet, 7-Scenario DM Playbook, Fragmentation Audit, and Ascension Map.\n\n' +
    '=== COMMUNITY CONTEXT ===\n' +
    'Name: ' + name + '\n' +
    'Members: ' + members + '\n' +
    'Platform: ' + platform + '\n' +
    'Biggest struggle: ' + struggleLabel + '\n' +
    'Weekly time available: ' + hours + ' hours\n\n' +
    '=== USER BUSINESS DNA ===\n' +
    'Niche: ' + niche + '\n' +
    'Avatar: ' + avatar + '\n' +
    'Offer: ' + offer + '\n\n' +
    '=== YOUR TASK ===\n' +
    'Run a full Community OS Audit with these 6 sections:\n\n' +
    '## 1. Community Health Score (0-100)\n' +
    'Score on 5 dimensions: Structure, Entry Positioning, Content Rhythm, Ascension Clarity, Buyer Signal Readiness.\n\n' +
    '## 2. The #1 Bottleneck\n' +
    'Based on the struggle "' + struggleLabel + '", identify the single root cause using the One Group Playbook.\n\n' +
    '## 3. The 7-Day Fix\n' +
    'A concrete 7-day plan that fits in ' + hours + ' hours. Each day: ONE action with a specific deliverable.\n\n' +
    '## 4. Weekly Community Ritual\n' +
    'Design a repeatable rhythm: 3-5 group posts + 10-20 DMs + 1 live touchpoint. List post types (Authority, Validation, Opener, Challenge, Authentic, DM Me, Outsource) and DM scenarios (Layup, Cry for Help, Hand Raiser, Thank You).\n\n' +
    '## 5. Buyer Signal Triggers\n' +
    'List 5 behaviors in ' + platform + ' that indicate readiness. For each: signal + exact first DM using S.I.P.E.\n\n' +
    '## 6. Ascension Path\n' +
    'Map free community -> paid offer. Give exact bridge post + bridge DM.\n\n' +
    'Be specific to ' + platform + ' and ' + niche + '. Every action under 20 minutes.';
}

document.addEventListener('DOMContentLoaded', function() {
  var btn = document.getElementById('cosAuditBtn');
  if (btn) {
    btn.addEventListener('click', function() {
      var prompt = cosBuildPrompt();
      var pb = document.getElementById('promptBox');
      var sub = document.getElementById('coachSubtitle');
      var modal = document.getElementById('coachModal');
      if (pb) pb.value = prompt;
      if (sub) sub.textContent = 'Community OS Audit';
      if (modal) modal.classList.remove('hidden');
    });
  }
});
