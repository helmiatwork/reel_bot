# frozen_string_literal: true

require "rails_helper"

RSpec.describe "Snoop", type: :request do
  describe "GET /snoop/targets" do
    it "returns empty targets array when no targets exist" do
      get "/snoop/targets"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to eq({ "targets" => [] })
    end

    it "returns list of targets with channel info and runs count" do
      target = SnoopTarget.create!(channel_id: "@techradar", handle: "@techradar", last_seen_video_id: "v123")
      SnoopResult.create!(channel_id: "@techradar", video_id: "v100")
      SnoopResult.create!(channel_id: "@techradar", video_id: "v123")

      get "/snoop/targets"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      targets = json["targets"]
      expect(targets.size).to eq(1)

      item = targets.first
      expect(item["channel_id"]).to eq("@techradar")
      expect(item["handle"]).to eq("@techradar")
      expect(item["last_seen_video_id"]).to eq("v123")
      expect(item["runs"]).to eq(2)
      expect(item["added_at"]).to be_present
      expect(item["created_at"]).to be_present
    end
  end

  describe "POST /snoop/targets" do
    it "creates a new target with raw channel_id and handle" do
      post "/snoop/targets", params: { channel_id: "UC12345", handle: "@tech" }, as: :json
      expect(response).to have_http_status(:created).or have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")
      expect(json["target"]["channel_id"]).to eq("UC12345")
      expect(json["target"]["handle"]).to eq("@tech")
    end

    it "parses and normalizes channel_id if a YouTube URL is provided" do
      post "/snoop/targets", params: { channel_id: "https://www.youtube.com/@mkbhd" }, as: :json
      expect(response).to have_http_status(:created).or have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")
      expect(json["target"]["channel_id"]).to eq("@mkbhd")
      expect(json["target"]["handle"]).to eq("@mkbhd")
    end

    it "returns 422 if channel_id is blank" do
      post "/snoop/targets", params: { channel_id: "" }, as: :json
      expect(response).to have_http_status(:unprocessable_entity)
      json = JSON.parse(response.body)
      expect(json["error"]).to be_present
    end

    it "returns 422 if channel_id is a duplicate" do
      SnoopTarget.create!(channel_id: "@mkbhd")
      post "/snoop/targets", params: { channel_id: "@mkbhd" }, as: :json
      expect(response).to have_http_status(:unprocessable_entity)
      json = JSON.parse(response.body)
      expect(json["error"]).to be_present
    end

    it "returns 422 if channel_id contains prohibited characters" do
      post "/snoop/targets", params: { channel_id: "@bad;rm -rf" }, as: :json
      expect(response).to have_http_status(:unprocessable_entity)
      json = JSON.parse(response.body)
      expect(json["error"]).to include("contains prohibited characters")
    end
  end

  describe "DELETE /snoop/targets/:channel_id" do
    it "deletes existing target and returns status ok" do
      target = SnoopTarget.create!(channel_id: "@veritasium", handle: "@veritasium")
      SnoopResult.create!(channel_id: "@veritasium", video_id: "vid_1")

      delete "/snoop/targets/@veritasium"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")

      expect(SnoopTarget.find_by(id: target.id)).to be_nil
      expect(SnoopResult.where(channel_id: "@veritasium")).to be_empty
    end

    it "supports case-insensitive channel_id lookup on delete" do
      target = SnoopTarget.create!(channel_id: "@MrBeast")
      delete "/snoop/targets/@mrbeast"
      expect(response).to have_http_status(:ok)
      expect(SnoopTarget.find_by(id: target.id)).to be_nil
    end

    it "returns 404 if target does not exist" do
      delete "/snoop/targets/nonexistent_channel"
      expect(response).to have_http_status(:not_found)
      json = JSON.parse(response.body)
      expect(json["error"]).to be_present
    end
  end

  describe "GET /snoop/results" do
    let!(:res1) { SnoopResult.create!(channel_id: "ch_1", video_id: "v1", created_at: 2.hours.ago) }
    let!(:res2) { SnoopResult.create!(channel_id: "ch_1", video_id: "v2", created_at: 1.hour.ago) }
    let!(:res3) { SnoopResult.create!(channel_id: "ch_2", video_id: "v3", created_at: 30.minutes.ago) }

    it "returns all results in recent order with default limit" do
      get "/snoop/results"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["results"].map { |r| r["video_id"] }).to eq([ "v3", "v2", "v1" ])
    end

    it "filters results by channel_id" do
      get "/snoop/results", params: { channel_id: "ch_1" }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["results"].map { |r| r["video_id"] }).to eq([ "v2", "v1" ])
    end

    it "clamps limit parameter between 1 and 200" do
      get "/snoop/results", params: { limit: 1 }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["results"].size).to eq(1)
      expect(json["results"].first["video_id"]).to eq("v3")
    end
  end

  describe "POST /snoop/results" do
    let!(:target) { SnoopTarget.create!(channel_id: "ch_watch", last_seen_video_id: "v_old") }

    it "records SnoopResult and advances target last_seen_video_id when clips is non-empty (RULE B3)" do
      clips_data = [
        { "start_sec" => 12, "end_sec" => 45, "title" => "Great hook" }
      ]

      post "/snoop/results", params: {
        channel_id: "ch_watch",
        video_id: "v_new",
        video_title: "Awesome Video",
        clips: clips_data
      }, as: :json

      expect(response).to have_http_status(:created).or have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")
      expect(json["result"]["video_id"]).to eq("v_new")
      expect(json["result"]["clips"]).to eq(clips_data)

      expect(target.reload.last_seen_video_id).to eq("v_new")
    end

    it "records SnoopResult but DOES NOT advance target last_seen_video_id when clips is empty array (RULE B3)" do
      post "/snoop/results", params: {
        channel_id: "ch_watch",
        video_id: "v_new",
        video_title: "Empty Video",
        clips: []
      }, as: :json

      expect(response).to have_http_status(:created).or have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")

      expect(target.reload.last_seen_video_id).to eq("v_old")
    end

    it "records SnoopResult but DOES NOT advance target last_seen_video_id when clips is nil (RULE B3)" do
      post "/snoop/results", params: {
        channel_id: "ch_watch",
        video_id: "v_new",
        video_title: "Nil Clips Video"
      }, as: :json

      expect(response).to have_http_status(:created).or have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")

      expect(target.reload.last_seen_video_id).to eq("v_old")
    end

    it "saves result successfully even if target does not exist" do
      post "/snoop/results", params: {
        channel_id: "ch_unknown",
        video_id: "v_orphan",
        video_title: "Orphan Video",
        clips: [ { "title" => "Clip" } ]
      }, as: :json

      expect(response).to have_http_status(:created).or have_http_status(:ok)
      expect(SnoopResult.find_by(video_id: "v_orphan")).to be_present
    end

    it "uses target channel_id casing when target matches case-insensitively" do
      SnoopTarget.create!(channel_id: "@TechReviewer", handle: "@TechReviewer")

      post "/snoop/results", params: {
        channel_id: "@techreviewer",
        video_id: "v_case_1",
        video_title: "Case Check Video",
        clips: []
      }, as: :json

      expect(response).to have_http_status(:created).or have_http_status(:ok)
      result = SnoopResult.find_by(video_id: "v_case_1")
      expect(result).to be_present
      expect(result.channel_id).to eq("@TechReviewer")
    end

    it "returns 422 if channel_id or video_id is missing" do
      post "/snoop/results", params: { channel_id: "ch_watch" }, as: :json
      expect(response).to have_http_status(:unprocessable_entity)

      post "/snoop/results", params: { video_id: "v123" }, as: :json
      expect(response).to have_http_status(:unprocessable_entity)
    end
  end
end
