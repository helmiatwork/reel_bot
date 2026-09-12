# frozen_string_literal: true

require "rails_helper"

RSpec.describe SnoopWatcherJob, type: :job do
  let(:youtube_service) { instance_double(YouTubeService) }
  let(:yt_dlp_service) { instance_double(YtDlpService) }
  let(:clip_finder_service) { instance_double(ClipFinderService) }

  before do
    allow(YouTubeService).to receive(:new).and_return(youtube_service)
    allow(YtDlpService).to receive(:new).and_return(yt_dlp_service)
    allow(ClipFinderService).to receive(:new).and_return(clip_finder_service)
  end

  describe "#perform" do
    let!(:target) do
      SnoopTarget.create!(channel_id: "@techcreator", handle: "@techcreator", last_seen_video_id: "old_vid_1")
    end

    context "when a new video is detected and clipping succeeds with non-empty clips (RULE B3)" do
      let(:clips) do
        [
          {
            "start_sec" => 15,
            "end_sec" => 45,
            "title" => "Insane AI feature",
            "hook" => "Look at this",
            "why" => "High surprise factor",
            "rank" => 1,
            "recommended" => true
          }
        ]
      end

      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return({ video_id: "new_vid_2", title: "New AI Review" })
        allow(clip_finder_service).to receive(:call).and_return({
          youtube_url: "https://www.youtube.com/watch?v=new_vid_2",
          clips: clips
        })
      end

      it "discovers clips, creates SnoopResult, and advances target last_seen_video_id" do
        expect(ClipFinderService).to receive(:new)
          .with(youtube_url: "https://www.youtube.com/watch?v=new_vid_2")
          .and_return(clip_finder_service)

        expect { described_class.new.perform }
          .to change(SnoopResult, :count).by(1)

        result = SnoopResult.last
        expect(result.channel_id).to eq("@techcreator")
        expect(result.video_id).to eq("new_vid_2")
        expect(result.video_title).to eq("New AI Review")
        expect(result.clips).to eq(clips)

        expect(target.reload.last_seen_video_id).to eq("new_vid_2")
      end
    end

    context "when a new video is detected but clipping returns empty clips (RULE B3)" do
      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return({ video_id: "new_vid_3", title: "Podcast with no clips" })
        allow(clip_finder_service).to receive(:call).and_return({
          youtube_url: "https://www.youtube.com/watch?v=new_vid_3",
          clips: []
        })
      end

      it "creates SnoopResult with empty clips and DOES NOT advance last_seen_video_id" do
        expect { described_class.new.perform }
          .to change(SnoopResult, :count).by(1)

        result = SnoopResult.last
        expect(result.video_id).to eq("new_vid_3")
        expect(result.clips).to eq([])

        expect(target.reload.last_seen_video_id).to eq("old_vid_1")
      end
    end

    context "when a new video is detected but clipping raises an error (RULE B3)" do
      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return({ video_id: "new_vid_4", title: "Error Video" })
        allow(clip_finder_service).to receive(:call).and_raise(ClipFinderService::Error, "Bridge failure")
      end

      it "creates SnoopResult with empty clips and DOES NOT advance last_seen_video_id" do
        expect { described_class.new.perform }
          .to change(SnoopResult, :count).by(1)

        result = SnoopResult.last
        expect(result.video_id).to eq("new_vid_4")
        expect(result.clips).to eq([])

        expect(target.reload.last_seen_video_id).to eq("old_vid_1")
      end
    end

    context "when the latest video matches last_seen_video_id" do
      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return({ video_id: "old_vid_1", title: "Already Seen Video" })
      end

      it "does not run clipping or create result" do
        expect(ClipFinderService).not_to receive(:new)
        expect { described_class.new.perform }.not_to change(SnoopResult, :count)
        expect(target.reload.last_seen_video_id).to eq("old_vid_1")
      end
    end

    context "when no video is returned" do
      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return(nil)
        allow(yt_dlp_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return(nil)
      end

      it "does nothing for that target" do
        expect(ClipFinderService).not_to receive(:new)
        expect { described_class.new.perform }.not_to change(SnoopResult, :count)
      end
    end

    context "when YouTubeService fails or is unconfigured and falls back to YtDlpService" do
      let(:clips) { [ { "start_sec" => 0, "end_sec" => 30, "title" => "Dlp clip" } ] }

      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_raise(YouTubeService::NotConfigured, "No API key")
        allow(yt_dlp_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_return({ video_id: "dlp_vid_9", title: "YtDlp Title" })
        allow(clip_finder_service).to receive(:call).and_return({
          youtube_url: "https://www.youtube.com/watch?v=dlp_vid_9",
          clips: clips
        })
      end

      it "successfully retrieves video via YtDlpService fallback and processes it" do
        expect(yt_dlp_service).to receive(:latest_channel_video).with("@techcreator")
        expect { described_class.new.perform }.to change(SnoopResult, :count).by(1)

        result = SnoopResult.last
        expect(result.video_id).to eq("dlp_vid_9")
        expect(result.video_title).to eq("YtDlp Title")
        expect(target.reload.last_seen_video_id).to eq("dlp_vid_9")
      end
    end

    context "when one target errors out during channel checking" do
      let!(:target2) do
        SnoopTarget.create!(channel_id: "@goodchannel", handle: "@goodchannel", last_seen_video_id: nil)
      end

      before do
        allow(youtube_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_raise(StandardError, "Network explosion")
        allow(yt_dlp_service).to receive(:latest_channel_video)
          .with("@techcreator")
          .and_raise(StandardError, "YtDlp error")

        allow(youtube_service).to receive(:latest_channel_video)
          .with("@goodchannel")
          .and_return({ video_id: "good_vid", title: "Good Video" })
        allow(clip_finder_service).to receive(:call).and_return({
          youtube_url: "https://www.youtube.com/watch?v=good_vid",
          clips: [ { "title" => "Clip" } ]
        })
      end

      it "continues processing the remaining targets" do
        expect { described_class.new.perform }.to change(SnoopResult, :count).by(1)
        expect(target2.reload.last_seen_video_id).to eq("good_vid")
      end
    end
  end
end
