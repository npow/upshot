#!/usr/bin/env bash
# Register all AI/LLM newsletter RSS feeds.
# Run once: chmod +x scripts/register_feeds.sh && ./scripts/register_feeds.sh
set -euo pipefail

feeds=(
  # --- Technical / Research ---
  "https://www.interconnects.ai/"
  "https://magazine.sebastianraschka.com/"          # Ahead of AI
  "https://importai.substack.com/"
  "https://thegradient.pub/"
  "https://cameronrwolfe.substack.com/"
  "https://newsletter.maartengrootendorst.com/"
  "https://newsletter.ruder.io/"                    # NLP News (Sebastian Ruder)
  # deeplearning.ai/the-batch has no RSS feed (Next.js SPA)
  "https://aksh-garg.substack.com/"                 # AK's Substack
  "https://palindrome.substack.com/"
  "https://davidsummarizes.substack.com/"           # Davis Summarizes Papers
  "https://thealgorithmicbridge.substack.com/"
  "https://datamachina.substack.com/"

  # --- Industry / News ---
  "https://lastweekin.ai/"
  "https://the-decoder.com/"
  "https://venturebeat.com/category/ai/"
  "https://www.technologyreview.com/topic/artificial-intelligence/"
  "https://www.wired.com/tag/artificial-intelligence/"
  "https://thesequence.substack.com/"
  "https://turingpost.substack.com/"
  "https://aitechtidbits.substack.com/"             # AI Tidbits
  "https://aiweirdness.com/"
  "https://chinai.substack.com/"

  # --- AI Safety ---
  "https://newsletter.safe.ai/"                     # AI Safety Newsletter
  "https://newsletter.mlsafety.org/"                # ML Safety Newsletter

  # --- Engineering / Applied ---
  "https://www.latent.space/"
  "https://simonwillison.net/"
  "https://cobusgreyling.substack.com/"             # Chain of Thought
  "https://underfitted.substack.com/"
  "https://themlengineers.substack.com/"             # ML Engineer Newsletter
  "https://aiweekly.substack.com/"                  # True Positive Weekly

  # --- Labs / Official ---
  "https://openai.com/blog"
  "https://developers.openai.com/blog/"
  "https://deepmind.google/blog/"
  "https://blog.research.google/"
  "https://huggingface.co/blog"
  "https://bair.berkeley.edu/blog/"
  "https://jalammar.github.io/"

  # --- Research Groups ---
  "https://berkeleyrdi.substack.com/"               # Agentic AI Weekly (Berkeley RDI)
  "https://aicollective.substack.com/"              # The AI Collective Newsletter

  # --- General ---
  "https://elvissaravia.substack.com/"              # NLP Elvis
  "https://pub.towardsai.net/"
  "https://www.kdnuggets.com/"
  "https://buzzrobot.substack.com/"
  "https://artificialintelligencemadesimple.substack.com/" # AI Guide

  # --- Kill the Newsletter (no public RSS) ---
  "https://kill-the-newsletter.com/feeds/n3xge951mugqng0yi390.xml"      # Ben's Bites
  "https://kill-the-newsletter.com/feeds/979q2dloil2irxdwwj8s.xml"      # Superhuman AI
  "https://kill-the-newsletter.com/feeds/h42hw3e6rznjcowc8t22.xml"      # The Rundown AI
  "https://kill-the-newsletter.com/feeds/v0jofhvzob768s9rbgmj.xml"      # The Neuron
  "https://kill-the-newsletter.com/feeds/ojvsdbs02cj00n41debd.xml"      # TLDR AI
  "https://kill-the-newsletter.com/feeds/8nndh44ukeb3oa1s7f0c.xml"      # AlphaSignal

  # --- arXiv ---
  "http://export.arxiv.org/rss/cs.LG"
  "http://export.arxiv.org/rss/cs.CL"
  "http://export.arxiv.org/rss/cs.AI"
)

echo "Registering ${#feeds[@]} feeds..."
for url in "${feeds[@]}"; do
  echo "  → $url"
  upshot add "$url" || echo "    ⚠ failed, skipping"
done
echo "Done. Run 'upshot feeds' to verify."
