# frozen_string_literal: true

require "rails_helper"

RSpec.describe ClipFind, type: :model do
  let(:valid_url) { "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }

  describe "validations" do
    it "is valid with a valid youtube_url" do
      clip_find = described_class.new(youtube_url: valid_url)
      expect(clip_find).to be_valid
    end

    it "is invalid without a youtube_url" do
      clip_find = described_class.new(youtube_url: nil)
      expect(clip_find).not_to be_valid
      expect(clip_find.errors[:youtube_url]).to include("can't be blank")
    end

    it "is invalid with a blank youtube_url" do
      clip_find = described_class.new(youtube_url: "   ")
      expect(clip_find).not_to be_valid
      expect(clip_find.errors[:youtube_url]).to include("can't be blank")
    end

    describe "command injection and prohibited characters" do
      prohibited_urls = [
        "https://www.youtube.com/watch?v=123; rm -rf /",
        "https://www.youtube.com/watch?v=123 && echo hacked",
        "https://www.youtube.com/watch?v=123 | cat /etc/passwd",
        "https://www.youtube.com/watch?v=123`id`",
        "https://www.youtube.com/watch?v=123$(whoami)",
        "https://www.youtube.com/watch?v=123\nmalicious",
        "https://www.youtube.com/watch?v=123\rmalicious",
        "https://www.youtube.com/watch?v=123<script>",
        "https://www.youtube.com/watch?v=123>out"
      ]

      prohibited_urls.each do |bad_url|
        it "rejects URL with prohibited character: #{bad_url.inspect}" do
          clip_find = described_class.new(youtube_url: bad_url)
          expect(clip_find).not_to be_valid
          expect(clip_find.errors[:youtube_url]).to be_present
        end
      end
    end

    describe "URL scheme and host validation" do
      it "rejects non-HTTP/HTTPS schemes like ftp://" do
        clip_find = described_class.new(youtube_url: "ftp://example.com/video.mp4")
        expect(clip_find).not_to be_valid
      end

      it "rejects file:// URLs" do
        clip_find = described_class.new(youtube_url: "file:///etc/passwd")
        expect(clip_find).not_to be_valid
      end

      it "rejects URLs without a host" do
        clip_find = described_class.new(youtube_url: "https://")
        expect(clip_find).not_to be_valid
      end

      it "rejects completely malformed URLs" do
        clip_find = described_class.new(youtube_url: "not-a-url")
        expect(clip_find).not_to be_valid
      end

      it "handles URI parse errors gracefully" do
        allow(URI).to receive(:parse).and_raise(URI::InvalidURIError.new("bad uri"))
        clip_find = described_class.new(youtube_url: "https://example.com")
        expect(clip_find).not_to be_valid
        expect(clip_find.errors[:youtube_url]).to include("is an invalid URI")
      end
    end

    describe "clips default" do
      it "defaults clips to empty array" do
        clip_find = described_class.create!(youtube_url: valid_url)
        expect(clip_find.clips).to eq([])
      end
    end

    describe "model and cost_usd attributes" do
      it "persists model string and cost_usd decimal" do
        clip_find = described_class.create!(
          youtube_url: valid_url,
          model: "claude-sonnet-4-6",
          cost_usd: 0.05123,
          clips: [ { "start_sec" => 10, "end_sec" => 25, "title" => "Hook" } ]
        )
        clip_find.reload
        expect(clip_find.model).to eq("claude-sonnet-4-6")
        expect(clip_find.cost_usd).to eq(0.05123)
        expect(clip_find.clips.first["title"]).to eq("Hook")
      end
    end
  end

  describe "scopes and class methods" do
    describe ".recent" do
      it "orders records by created_at descending" do
        first = described_class.create!(youtube_url: "https://www.youtube.com/watch?v=first", created_at: 2.hours.ago)
        second = described_class.create!(youtube_url: "https://www.youtube.com/watch?v=second", created_at: 1.hour.ago)

        expect(described_class.recent.pluck(:id)).to eq([ second.id, first.id ])
      end
    end

    describe ".latest_for" do
      it "returns the most recent record for a specific URL" do
        older = described_class.create!(youtube_url: valid_url, created_at: 2.hours.ago, clips: [ { "title" => "old" } ])
        newer = described_class.create!(youtube_url: valid_url, created_at: 10.minutes.ago, clips: [ { "title" => "new" } ])
        other = described_class.create!(youtube_url: "https://www.youtube.com/watch?v=other", created_at: 5.minutes.ago)

        expect(described_class.latest_for(valid_url)).to eq(newer)
      end

      it "returns nil when no record exists for the URL" do
        expect(described_class.latest_for("https://www.youtube.com/watch?v=nonexistent")).to be_nil
      end
    end
  end
end
