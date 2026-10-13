MARIAH COZ - HIGH TICKET HYBRID
## : Complete Group Coaching Operations System

Source: Mariah Coz - High Ticket Hybrid 
Category: Group Coaching / Program Operations / Client Management
Last Updated: March 2026

---

## PART 1 OVERVIEW

| Section | Focus |
|---------|-------|
| Tech & Software Foundation | Required tools setup |
| AirTable Bases | Lead and client management |
| Zapier Automations | Automated workflows |
| Client Onboarding | Welcome process |
| Client Lifecycle | Renewals and offboarding |
| Difficult Clients | Response templates |
| Group Call Delivery | Q&A and Critique calls |
| Facebook Group | Community management |
| Milestone Calls | Client recognition |

---

## 1. TECH & SOFTWARE FOUNDATION

### 1.1 Required Software

| Tool | Purpose | Plan |
|------|---------|------|
| Zapier | Connect apps, automate workflows | Starter plan |
| AirTable | CRM for leads & clients | Pro Plan (custom branding) |
| Deadline Funnel | Countdown timers | First month free for new users |

### 1.2 Optional Software

| Tool | Purpose |
|------|---------|
| LeadPages | Landing pages for applications |
| ScheduleOnce | Onboarding and milestone scheduling |

---

## 2. AIRTABLE BASES

### 2.1 The Two Main Bases

| Base | Purpose |
|------|---------|
| Program: Leads | Lead pipeline, application process |
| Program: Clients | Delivery tracking, enrolled clients |

**The Flow:**
```
Lead → Applies → Accepted → Moves from Leads Base to Clients Base
```

### 2.2 Leads Base Structure

- Applications tab
- Status tracking
- Communication history
- Funnel source data

### 2.3 Clients Base Structure

- Client profiles
- Enrollment dates
- Payment status
- Milestone tracking
- End date formula (auto-calculates based on program length)

---

## 3. ZAPIER AUTOMATIONS

### 3.1 Application Notification Zap

**Trigger:** New Record in AirTable (Applications table)

**Actions:**

| Step | Action |
|------|--------|
| 1 | Add Subscriber to Sequence (ConvertKit) |
| 2 | Add Tag: "[PROGRAM] - Applied" |
| 3 | Send Slack notification |

**Slack Message Template:**

```
NEW [PROGRAM] APPLICATION 👏👏👏

Name: [Name Field from AirTable]
Link: [Workspace URL]/[Record Field from AirTable]
```

### 3.2 Student Onboarding Zap

**Prerequisites:**
- Checkout links and product IDs
- Contract in HelloSign
- Courses in Teachable
- Client AirTable Base created
- Welcome Sequence in email platform

**Automations:**
- Create client record in Clients Base
- Send contract via HelloSign
- Enroll in Teachable courses
- Add to Welcome Sequence
- Add to Facebook Group
- Notify team in Slack

---

## 4. CLIENT ONBOARDING

### 4.1 Program Welcome Email

```
Hey [Name],

Welcome to the [Program Name]! We're thrilled you're here!

**1. Sign the Program Agreement**
The first thing you need to do is sign the Program Agreement sent to you 
via HelloSign. Please sign within the next 24 hours.

**2. Book your Orientation Call**
One of our team would love to hop on a call with you over the next 48 hours 
to walk you through the Program and answer any questions.

Schedule your call here: [booking link]

**3. Access the Program**
The training materials are hosted on [platform]. You should have received 
emails with login information. Access at: [course URL]

**4. Complete the Intake Form**
Your first assignment! Please fill out the Intake Questionnaire within 72 hours:
[intake form link]

**5. Join the Facebook Group**
Request to join our private group here: [FB group link]

We can't wait to support you!

xx
[Your Name]
```

### 4.2 Pay In Full Bonus Email

```
Subject: Your Bonus 1:1 Strategy Session ✨

Hi [Name],

As a benefit of paying in full, you have the ability to schedule a 
**60-minute 1:1 Strategy Session** with one of our coaches.

This is a fantastic opportunity to get personalized support on 
[program milestones or specifics].

**To book your 1:1 Strategy Session:**
1. Use this [scheduleonce link] to select a time
2. Fill out [this form] so we can prepare

You have a full year to use this – but if you're planning to use it right away, 
just ensure you've completed your onboarding call first.

We can't wait to support you!

[Your Name]
```

### 4.3 Onboarding Call SOP

**Call Length:** 15 minutes

**Before the Call:**

1. Client receives automated welcome email with booking link
2. Call is scheduled based on coach availability
3. Coach reviews application and intake form
4. Coach confirms active tag in email system
5. Coach opens Teachable, Facebook group, relevant pages

**Call Agenda:**

| Step | Activity |
|------|----------|
| 1 | Introduce self, welcome client |
| 2 | Ask: "What was the catalyst for you joining?" |
| 3 | Ask: "What are your goals for the next X months?" |
| 4 | Screen-share Teachable walkthrough |
| 5 | Reaffirm: Coaches are champions of your success |
| 6 | Reiterate: It will feel overwhelming – use your WHY |
| 7 | Ask: "Barriers to success? Strengths? Questions?" |
| 8 | Explain Facebook group purpose |
| 9 | Give 2-3 immediate action steps |

**After the Call:**
- Record in AirTable that Onboarding Call complete
- Follow up on any promised items

---

## 5. CLIENT LIFECYCLE

### 5.1 The 60-Day Timeline

| Timeline | Action |
|----------|--------|
| 60 days prior | Send Program Check-In & Reminder email |
| 30 days prior | Send Continuation Offer / Renewal email |
| 5 days prior | Send Removal & Downsell email |
| 1 day post-expiry | Remove from tech, send final goodbye |

### 5.2 Renewal Email Template

```
Subject: ⏱ Your time in [Program Name] (what's next...)

Hey [Name],

Just popping in with a quick update!

**Looking ahead, your first [time period] in [Program Name] ends on [Date], 
and I'd love to chat about next steps!**

It has been amazing working with you! You've made a huge leap forward in 
[personalized wins] and I'm so excited to chat about what's next.

**Good news: after the first [length], it doesn't have to end!**

After your initial [length], you can stay in the Program for another [renewal period] 
with this exclusive offer:

**$XXX pay in full (save $XXX)**
**OR $XXX monthly payment plan (save $XXX)**

*The Pay in Full option also includes a 60-minute strategy call with one of our coaches!*

[Renewal link]

**This offer is only valid if you choose to renew before your [length] expires.** 
If you come back later after a break, you'll come back at regular full price.

We're always adding new things to the program, so there are great perks to staying around!

Do you plan on staying with us? If I can answer any questions, please reach out.

Xx
[Your Name] & Team
```

### 5.3 Removal & Downsell Email (5 Days Before)

```
Subject: Your time in [Program Name] is almost up!

Hey [Name],

What an incredible [length] you've had within [Program Name]! Your time is almost up 
and you've let us know that you won't be continuing on with us. (We'll miss you!)

We have absolutely loved having you as a part of the program and hope you have gained 
[outcomes of the Program].

**REMINDER:** If you haven't already, you can book your 1:1 Graduation Call when you 
[fill out this Program Exit Survey]!

We'd especially love to hear about your [personalized wins].

Your time in [Program Name] officially ends in a few days on [Date].

[Optional downsell offer with link]

Again, congratulations on completing your [length] inside [Program Name].

We wish you all the best for your continued success!

xx
[Your Name]
```

### 5.4 Exit Survey Questions

1. *Describe your life & business prior to joining [Program Name]*
   - Prompt: How were you feeling? What was holding you back?

2. *What were some of your biggest results and #wins during [Program Name]?*
   - Prompt: Be specific – revenue wins, mindset shifts, favorite results

3. *What would you tell someone who's thinking about joining?*

4. *Any last feedback, insights or love you'd like to share?*

5. *Ideas for things we can add?*

### 5.5 Post-Expiry Removal

**Tech Steps:**

| Platform | Action |
|----------|--------|
| Teachable | Unenroll from bundle |
| AirTable | Update status to "Completed - Did Not Renew" |
| ConvertKit | Remove course tags |
| Facebook | Remove from group |

**Final Email:**

```
Subject: Your time inside [Program Name] has come to an end!

Hey [Name],

Just letting you know that you've been removed from the Facebook Group, 
courses within Teachable, and any program-related emails.

We'd love it if you could please take a few minutes to fill out this 
super quick survey [HERE] to give us your genuine feedback.

Again, thank you for being a part of [Program Name]!

[Your Name] x
```

---

## 6. DIFFICULT CLIENT SITUATIONS

### 6.1 Unsatisfied Client Response

**Structure:**

1. Acknowledge and validate
2. Reiterate issues, respond directly
3. Offer next steps
4. List available resources
5. Propose 1:1 call

**Key Section:**

```
We understand how you're feeling. Here's what we would like to do next to get back on track!

One of our coaches would love to hop on a 1:1 call with you to come up with 
a personalized action plan.

We definitely don't want you feeling overwhelmed as there are incredible resources available to you 
that you haven't utilized to the fullest yet! Those include Weekly Critique Calls, Coaching Calls, 
Milestone Calls, and of course the training and content.

We find that those within [Program Name] who see the best results are those who take radical 
personal responsibility, go through ALL the content, show up to the calls, and stay active.
```

**Available Resources:**
- Weekly Critique Calls
- Weekly Q&A Calls
- 1:1 Milestone Calls
- Trainings and content

### 6.2 Not Hitting Milestones Response

```
Subject: Hi [Name], Thank you for your Email!

Hi [Name],

Thank you for reaching out and sharing your thoughts. We truly hear you and 
understand your frustrations over your recent [launch/results].

We understand it might be hard to see now, but having tried something that didn't work 
will help you get even clearer on an offer that does.

Our successes and failures are part of the journey. It's normal to experience setbacks.

[Include detailed feedback specific to situation]

We can regroup, have your post-launch milestone call to assess everything, come up with 
a plan for what offer would appeal to your audience, and go forward.

We are here to help you. Lots of our successful clients had many hiccups and setbacks.

[Booking your Post-Launch Milestone Call] is the best way to talk through these ideas.

Best,
[Your Name + team]
```

### 6.3 Early Exit Request Response

```
Hey [Name],

Thank you for reaching out. We pride ourselves on being accessible and supportive. 
We don't like to see anyone struggling in silence.

I want to acknowledge your note and how you are feeling. I can tell it took a lot 
for you to reach out and we are happy you did. Resistance can show up in many 
different ways and at any time. I would love to connect with you to get a better 
understanding of misalignments.

We also want to be transparent. The application process was created to help us 
select participants that we believe are a fit. We saw this in your application 
for sure! As stated in the contract, we do not offer refunds in the [Program Name].

However, we are here to make sure you get the most out of this experience. 
We are here to support you in every way!

Again, I would love to explore the misalignment and resistance you are feeling 
in further detail. It's my sincere hope that we can come up with a solution that 
helps you move forward confidently.

Let's hop on a call to discuss this in detail as soon as you can. Here is 
[my link] to book a check-in with me.

I look forward to connecting soon.

xx
[Coach]
```

### 6.4 Financial Hardship Response (Last Resort)

```
Hey [Name],

Thanks so much for reaching out and sharing such a vulnerable 
time in your business. I really appreciate you letting me know where you're at.

It's one of my values to never put our students in a place of financial hardship, 
and I also want to honor the contracts and commitments we put in place.

I'm happy to make a one-time exception and have you pay off the program when you can, 
even if that's 6-9+ months from now. My team will remove your access from the program 
and pause your payments. When you're in a better financial place, email us and we'll 
enroll you back into the program and you can resume paying off the remainder.

Please keep this agreement between you and I because this is a truly special exception 
that I don't make for other people.

Let me know if you need any further clarification.

Xx,
[Your Name + team]
```

---

## 7. GROUP CALL DELIVERY

### 7.1 Q&A Call SOP

**Details:**
- Frequency: Weekly, bi-weekly, or monthly
- Length: 60 minutes (90 max)
- Platform: Zoom (recurring link)

**Before Call:**

1. **1 month - 1 week - 1 day before:** Encourage attendance via email and Facebook

**Reminder Email:**

```
Subject: Reminder: [Program] Call is tomorrow!

Hey friends!

Just a reminder that our upcoming Q&A call is tomorrow!

[Click HERE to access the Zoom Link!]

Date: [Date]
Time: [Time] Eastern / [Time] Central

[Don't forget to ask your questions HERE.]

See you there!
xx
[Your Name] & team
```

**Day of Call:**

1. Test call link
2. Compile pre-submitted questions from AirTable into Call Notes
3. Vet questions (remove those better suited elsewhere)
4. Note new clients for introductions

**On the Call:**

| Time | Activity |
|------|----------|
| Start | ENSURE CALL IS RECORDING |
| Welcome | Welcome clients verbally |
| Engagement | "Share a win, gratitude, project, or question in the chat!" |
| | Paste: W: Win? G: Grateful? P: Working on? Q: Need? |
| Introductions | Welcome new clients |
| Q&A | Read questions, answer |
| Throughout | Mute as they join, screenshot testimonials, timestamp (⏱️ MM:SS) |

**After Call:**

1. Prepare Replay Description with timestamps
2. Upload to Facebook and/or Teachable
3. Tag clients by name
4. Archive to Google Drive

### 7.2 Critique Call SOP

**Purpose:** In-depth feedback on client assets

**Details:**
- Frequency: Weekly or bi-weekly
- Length: 60-90 minutes
- Platform: Zoom (screen share)

**Before Call:**

1. Encourage attendance
2. Day of: Compile submissions, open URLs in tabs

**On the Call:**

| Time | Activity |
|------|----------|
| Start | ENSURE RECORDING |
| Welcome | Welcome clients |
| Review | Share screen, read question, give feedback |
| Prioritize | If clients attend live, review their work first |
| Throughout | Timestamp, monitor chat |
| End | Mark submissions "Resolved" in AirTable |

**After Call:**

1. Prepare Replay Description
2. Upload and tag
3. Archive

### 7.3 Call Notes Templates

**Q&A Call:**

```
## [Program] - Q&A Call Notes
## [Month Day, Year]

### AGENDA:

- **Share:** W: Win? G: Grateful? P: Project? Q: Need?

- **Introductions / Housekeeping:**

- **Pre-Submitted Questions:**
  - Name ⏱️ (::) - Question

- **Live Questions:**
  - Name ⏱️ (::) - Question

**Team Notes / Post-Call Follow-up:**
```

**Critique Call:**

```
## [Program] - Critique Call Notes
## [Month Day, Year]

**Submitted Work:**

- **Name (::)** -
  - **Work submitted:**
  - **Q**:
  - **URL**:
```

---

## 8. FACEBOOK GROUP MANAGEMENT

### 8.1 Group Rules

1. **Give value and promote discussion.** Share wins, ask questions, answer questions.

2. **Keep it positive and respectful.** If you don't agree, scroll on.

3. **No promotional material.** Share progress, not promotions.

4. **We are here to support you!** For customer service, email support@.

*My team and I answer questions M-F, 10 am - 2 pm ET. We do not check on weekends.*

### 8.2 Group Description

```
Welcome to the group! We're so excited to have you in the [Program]!

We love this group and the level of enthusiasm, positivity, and support 
that everyone brings to the table.

My team and I answer questions in the group M-F, between 10 am and 2 pm ET. 
We do not check the group on weekends.

We may decide that your question is better suited to a Coaching or Critique Call, 
and we'll let you know.

This group is not the place for customer support (billing, log in issues) – 
please email support@ for those.

Here are a few guidelines:

+ Give value and promote discussion. Share your wins, ask questions, answer questions!
+ Keep it positive and respectful. If you don't agree, simply scroll on.
+ No promotional material. Share progress, not promotions.
+ We are here to support you! For customer service, email support@.

We are so glad you're here!
xx, [Name] and Team
```

### 8.3 Master FAQ Post

```
** 🎉 MASTER FAQ: Please Read! 🎉 **

Welcome to the Program! Below are frequently asked questions.

🕒 When is the weekly call?
Wednesdays from 2 - 3 pm Eastern. We create weekly Facebook events and send email reminders.

➡️ How do I submit questions?
Through this form: [link]

❓ How do I watch replays?
We upload replays within 48 hours.

📅 What day/time are modules released?
Every 7 days after you enroll.

❓ Do you have a referral program?
Yes! If you refer someone who enrolls (and stays), you earn a commission.

Thank you! 🎉🚀
```

### 8.4 Pre-Made Posts

**Q&A Call Reminder:**

```
Happy Q&A Call Day! 

Don't forget to get those burning questions in 👇 at least 30 mins before we go live!

[Insert Airtable Link]

See you there or on the replay!
```

**Critique Call Reminder:**

```
✨ Reminder: We've got our weekly Critique Call today at 9am EST! ✨

There's still space for you to submit work for review 👇 at least 30 mins before we go live!

[Insert Airtable Link]

See you there or on the replay!
```

**Celebrate Your Wins:**

```
🎉🎉 SHARE YOUR WINS 🎉🎉

What are you proud of this week? What goals have you smashed? How can we celebrate with you?!

We absolutely LOVE to see your successes!
```

**What Are You Working On:**

```
We'd LOVE to know what you're busily working on so we can get our pom poms out 
and CHEER you on! 🤸‍♀️🎉

Share your WINS / PROJECTS / or let us know where you're needing extra support...
```

### 8.5 Response Library

**Purpose:** Maintain approved responses for common questions

**How It Works:**
- When question is answered well, copy/paste into Airtable "FB Response Library"
- Coaches can access canned responses
- Essential for training new hires

---

## 9. MILESTONE CALLS & GIFTS

### 9.1 Milestone Call Process

```
Client books via ScheduleOnce → 
Redirected to Milestone Form → 
Coach reviews submission → 
Call conducted → 
Follow-up as needed
```

**Reminder Tactics:**
- Monthly Facebook reminders with scheduling link
- Comment on win posts with reminder to book

### 9.2 Milestone Gift Form Fields

- What Milestone are we celebrating?
  - Revenue: $10K-$99K, $100K-$499K, $500K-$999K, $1M+
  - Other: Did webinar, Launched course, 1,000 subscribers, Evergreen live

- Full Name
- Mailing Address
- What are some wins you experienced?
- How did the content help you?
- How are you celebrating?
- Attach screenshot of proof

### 9.3 Gift Services

| Region | Service |
|--------|---------|
| US | Greetabl |
| Australia | Thankly |

### 9.4 Milestone Call Scripts

**15-Min Rapid Validation Debrief:**

- How many registered for webinar?
- How many attended live?
- How many purchased during webinar?
- How many enrolled total?
- Did your idea validate?
- What are some wins?
- What are you proud of?
- What are you grateful for?
- How are you feeling?

**30-Min Course Launch Debrief:**

- What was your revenue goal?
- How much revenue did you make?
- How many enrolled?
- Did you send all emails?
- Did you do all live streams?
- How many registered/attended webinar?
- What went awesome that you'd do again?
- What needs improvement?
- What did not go well that you won't do again?
- What are some wins?
- What are you proud of?
- What are you grateful for?
- How are you celebrating?
- How are you feeling?

**20-Min Funnel Debrief:**

- What type of funnel?
- How much traffic?
- What are your lead magnets?
- How are you driving traffic?
- What is conversion rate?
- What needs improvement?
- What are you pleased with?

---

## QUICK REFERENCE FOR INCOME ENGINE

### Your Group Program Tech Stack

| Tool | Purpose |
|------|---------|
| Zapier | Automations |
| AirTable | Leads + Clients CRM |
| Deadline Funnel | Countdown timers |
| ScheduleOnce | Onboarding + Milestone calls |
| ConvertKit | Email sequences |
| HelloSign | Contracts |
| Teachable | Course hosting |
| Zoom | Live calls |
| Slack | Team notifications |

### Your Client Lifecycle Timeline

| Day | Action |
|-----|--------|
| Day 0 | Enrollment → Welcome email |
| Day 1-2 | Onboarding call |
| Day 1-72 | Intake form completion |
| Ongoing | Weekly calls, Facebook engagement |
| Milestone achieved | Milestone call + gift |
| 60 days before end | Renewal email |
| 30 days before | Renewal offer |
| 5 days before | Removal email |
| 1 day after | Remove from tech |

### Your Onboarding Email Checklist

- [ ] Program welcome email
- [ ] PIF bonus email (if applicable)
- [ ] Onboarding call booking
- [ ] Intake form link
- [ ] Facebook group join
- [ ] Teachable login info

### Your Group Call Rhythm

| Call Type | Frequency | Length |
|-----------|-----------|--------|
| Q&A Call | Weekly | 60 min |
| Critique Call | Weekly | 60-90 min |
| Milestone Call | As achieved | 15-30 min |

---

## INTEGRATION WITH OTHER FRAMEWORKS

| Layer | Source | How High Ticket Hybrid Enhances |
|-------|--------|--------------------------------|
| Funnel Building | Jessica Tutton | Add application funnel for group program |
| Email Sequences | Jim Hamilton | Add onboarding + renewal sequences |
| Brand Voice | Alex Cattoni | Consistent voice across group communications |
| Consulting | Laura Meyer | Add GROUP model to 1:1 model |
| Content | Jessica DeRose | Content feeds group engagement |
| Tech Automation | Steve Mellor | Complete AirTable + Zapier system |

---

## ACTION CHECKLIST

### Week 1

- [ ] Sign up for Zapier, AirTable, Deadline Funnel
- [ ] Create Leads Base
- [ ] Create Clients Base

### Week 2

- [ ] Set up Application Notification Zap
- [ ] Set up Student Onboarding Zap
- [ ] Create welcome email templates

### Week 3

- [ ] Set up ScheduleOnce
- [ ] Create onboarding call SOP
- [ ] Create intake form

### Week 4

- [ ] Set up Facebook group
- [ ] Create group rules
- [ ] Create response library

### Week 5

- [ ] Set up Q&A call SOP
- [ ] Set up Critique call SOP
- [ ] Create call note templates

### Week 6

- [ ] Set up Milestone call system
- [ ] Create milestone forms
- [ ] Set up Greetabl/Thankly

---

## THE BOTTOM LINE

Group coaching = scale without burnout

Tech foundation = Zapier + AirTable + Deadline Funnel

Onboarding = Welcome email + 48-hour call + intake form

Client lifecycle = 60-30-5-1 timeline

Difficult clients = Acknowledge + offer path forward

Group calls = Q&A (60 min) + Critique (60-90 min)

Facebook group = Clear rules + response hours + response library

Milestones = Calls + gifts = recognition + data

**The operational layer that makes group programs scalable.**

---

END OF FILE
```
