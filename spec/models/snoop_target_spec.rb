# frozen_string_literal: true

require "rails_helper"

RSpec.describe SnoopTarget, type: :model do
  describe "validations" do
    it "is valid with a channel_id" do
      target = described_class.new(channel_id: "UC123456789")
      expect(target).to be_valid
    end

    it "is invalid without a channel_id" do
      target = described_class.new(channel_id: nil)
      expect(target).not_to be_valid
      expect(target.errors[:channel_id]).to include("can't be blank")
    end

    it "is invalid with a blank channel_id" do
      target = described_class.new(channel_id: "   ")
      expect(target).not_to be_valid
      expect(target.errors[:channel_id]).to include("can't be blank")
    end

    it "enforces uniqueness of channel_id case-insensitively" do
      described_class.create!(channel_id: "@TechChannel")
      duplicate = described_class.new(channel_id: "@techchannel")
      expect(duplicate).not_to be_valid
      expect(duplicate.errors[:channel_id]).to include("has already been taken")
    end

    it "rejects channel_id containing prohibited command injection characters" do
      prohibited = [ ";", "&", "|", "`", "$", "\n", "\r", "<", ">" ]
      prohibited.each do |char|
        target = described_class.new(channel_id: "UC123#{char}exploit")
        expect(target).not_to be_valid
        expect(target.errors[:channel_id]).to include("contains prohibited characters")
      end
    end

    it "rejects channel_id with invalid characters such as spaces or slashes" do
      invalid_inputs = [ "channel with space", "foo/bar", "invalid#hash", "@!invalid" ]
      invalid_inputs.each do |input|
        target = described_class.new(channel_id: input)
        expect(target).not_to be_valid
        expect(target.errors[:channel_id]).to include("is invalid")
      end
    end

    it "accepts valid channel identifiers" do
      valid_inputs = [
        "@techcreator",
        "@Channel.Name-123",
        "UC1234567890123456789012",
        "simple_channel_slug"
      ]
      valid_inputs.each do |input|
        target = described_class.new(channel_id: input)
        expect(target).to be_valid
      end
    end

    it "rejects YouTube URLs containing command injection characters" do
      target = described_class.new(channel_id: "https://www.youtube.com/@mkbhd; rm -rf /")
      expect(target).not_to be_valid
      expect(target.errors[:channel_id]).to include("contains prohibited characters")
    end
  end

  describe "associations" do
    it "has many snoop_results using channel_id foreign key" do
      target = described_class.create!(channel_id: "UC_target_assoc")
      result1 = SnoopResult.create!(channel_id: "UC_target_assoc", video_id: "vid_1")
      result2 = SnoopResult.create!(channel_id: "UC_target_assoc", video_id: "vid_2")

      expect(target.snoop_results).to contain_exactly(result1, result2)
    end

    it "destroys associated snoop_results when target is destroyed" do
      target = described_class.create!(channel_id: "UC_target_destroy")
      SnoopResult.create!(channel_id: "UC_target_destroy", video_id: "vid_1")

      expect { target.destroy }.to change(SnoopResult, :count).by(-1)
    end
  end

  describe "scopes" do
    it ".recent orders targets by created_at descending" do
      t1 = described_class.create!(channel_id: "UC_old", created_at: 2.days.ago)
      t2 = described_class.create!(channel_id: "UC_new", created_at: 1.day.ago)

      expect(described_class.recent.pluck(:channel_id)).to eq([ t2.channel_id, t1.channel_id ])
    end
  end

  describe "normalization helper" do
    describe ".normalize_channel_input" do
      it "extracts handle from a full youtube.com/@handle URL" do
        parsed = described_class.normalize_channel_input("https://youtube.com/@mkbhd")
        expect(parsed[:handle]).to eq("@mkbhd")
        expect(parsed[:channel_id]).to eq("@mkbhd")
      end

      it "extracts handle from www.youtube.com/@handle with trailing query parameters" do
        parsed = described_class.normalize_channel_input("https://www.youtube.com/@veritasium?si=xyz123")
        expect(parsed[:handle]).to eq("@veritasium")
        expect(parsed[:channel_id]).to eq("@veritasium")
      end

      it "extracts channel ID from youtube.com/channel/UC... URL" do
        parsed = described_class.normalize_channel_input("https://www.youtube.com/channel/UC1234567890abcdef")
        expect(parsed[:channel_id]).to eq("UC1234567890abcdef")
      end

      it "handles raw @handle strings" do
        parsed = described_class.normalize_channel_input("@mrbeast")
        expect(parsed[:handle]).to eq("@mrbeast")
        expect(parsed[:channel_id]).to eq("@mrbeast")
      end

      it "handles raw channel ID strings" do
        parsed = described_class.normalize_channel_input("UCBJycsmduvYEL83R_U4JriQ")
        expect(parsed[:channel_id]).to eq("UCBJycsmduvYEL83R_U4JriQ")
      end
    end

    it "auto-normalizes channel_id and handle before validation when given a URL" do
      target = described_class.new(channel_id: "https://www.youtube.com/@mkbhd")
      target.valid?
      expect(target.channel_id).to eq("@mkbhd")
      expect(target.handle).to eq("@mkbhd")
    end

    it "prepends @ to handle if handle does not start with @" do
      target = described_class.new(channel_id: "UC123", handle: "techcreator")
      target.valid?
      expect(target.handle).to eq("@techcreator")
    end
  end
end
