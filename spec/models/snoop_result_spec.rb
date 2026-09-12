# frozen_string_literal: true

require "rails_helper"

RSpec.describe SnoopResult, type: :model do
  describe "validations" do
    it "is valid with channel_id and video_id" do
      result = described_class.new(channel_id: "UC123", video_id: "vid_xyz")
      expect(result).to be_valid
    end

    it "is invalid without channel_id" do
      result = described_class.new(channel_id: nil, video_id: "vid_xyz")
      expect(result).not_to be_valid
      expect(result.errors[:channel_id]).to include("can't be blank")
    end

    it "is invalid without video_id" do
      result = described_class.new(channel_id: "UC123", video_id: nil)
      expect(result).not_to be_valid
      expect(result.errors[:video_id]).to include("can't be blank")
    end
  end

  describe "associations" do
    it "belongs to snoop_target optionally" do
      result = described_class.new(channel_id: "nonexistent_channel", video_id: "vid_1")
      expect(result).to be_valid

      target = SnoopTarget.create!(channel_id: "UC_has_target")
      result.channel_id = target.channel_id
      expect(result.snoop_target).to eq(target)
    end
  end

  describe "scopes" do
    it ".recent orders results by created_at descending" do
      r1 = described_class.create!(channel_id: "UC1", video_id: "v1", created_at: 2.hours.ago)
      r2 = described_class.create!(channel_id: "UC1", video_id: "v2", created_at: 1.hour.ago)

      expect(described_class.recent.pluck(:video_id)).to eq([ r2.video_id, r1.video_id ])
    end
  end

  describe "defaults" do
    it "defaults clips to empty array" do
      result = described_class.create!(channel_id: "UC1", video_id: "v1")
      expect(result.clips).to eq([])
    end

    it "persists json clips array" do
      clips_data = [
        { "start_sec" => 10, "end_sec" => 40, "title" => "Great hook", "recommended" => true }
      ]
      result = described_class.create!(channel_id: "UC1", video_id: "v1", clips: clips_data)
      expect(result.reload.clips).to eq(clips_data)
    end
  end
end
