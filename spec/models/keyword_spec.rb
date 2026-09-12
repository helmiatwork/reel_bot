# frozen_string_literal: true

require "rails_helper"

RSpec.describe Keyword, type: :model do
  describe "validations" do
    subject(:keyword) { build(:keyword) }

    it "is valid with valid attributes" do
      expect(keyword).to be_valid
    end

    it "validates presence of keyword" do
      keyword.keyword = nil
      expect(keyword).not_to be_valid
      expect(keyword.errors[:keyword]).to include("can't be blank")
    end

    it "validates presence of source" do
      keyword.source = nil
      expect(keyword).not_to be_valid
      expect(keyword.errors[:source]).to include("can't be blank")
    end

    it "validates presence of region" do
      keyword.region = nil
      expect(keyword).not_to be_valid
      expect(keyword.errors[:region]).to include("can't be blank")
    end
  end

  describe "scopes" do
    let!(:kw1) do
      create(:keyword,
             keyword: "kw1",
             score: 100.0,
             niche: "tech",
             source: "google_ads",
             region: "ID:id",
             avg_monthly_searches: 1000)
    end
    let!(:kw2) do
      create(:keyword,
             keyword: "kw2",
             score: 500.0,
             niche: "finance",
             source: "youtube_suggest",
             region: "US:en",
             avg_monthly_searches: 5000)
    end
    let!(:kw3) do
      create(:keyword,
             keyword: "kw3",
             score: 250.0,
             niche: "tech",
             source: "google_ads",
             region: "US:en",
             avg_monthly_searches: 2500)
    end

    describe ".by_score" do
      it "orders records by score descending" do
        expect(described_class.by_score).to eq([ kw2, kw3, kw1 ])
      end
    end

    describe ".by_niche" do
      it "filters by niche when niche is present" do
        expect(described_class.by_niche("tech")).to contain_exactly(kw1, kw3)
        expect(described_class.by_niche("finance")).to contain_exactly(kw2)
      end

      it "returns all records when niche is blank or nil" do
        expect(described_class.by_niche(nil)).to contain_exactly(kw1, kw2, kw3)
        expect(described_class.by_niche("")).to contain_exactly(kw1, kw2, kw3)
      end
    end

    describe ".by_source" do
      it "filters by source when source is present" do
        expect(described_class.by_source("google_ads")).to contain_exactly(kw1, kw3)
        expect(described_class.by_source("youtube_suggest")).to contain_exactly(kw2)
      end

      it "returns all records when source is blank or nil" do
        expect(described_class.by_source(nil)).to contain_exactly(kw1, kw2, kw3)
        expect(described_class.by_source("")).to contain_exactly(kw1, kw2, kw3)
      end
    end

    describe ".by_region" do
      it "filters by region when region is present" do
        expect(described_class.by_region("ID:id")).to contain_exactly(kw1)
        expect(described_class.by_region("US:en")).to contain_exactly(kw2, kw3)
      end

      it "returns all records when region is blank or nil" do
        expect(described_class.by_region(nil)).to contain_exactly(kw1, kw2, kw3)
        expect(described_class.by_region("")).to contain_exactly(kw1, kw2, kw3)
      end
    end

    describe ".min_volume" do
      it "filters by minimum avg_monthly_searches when vol is present" do
        expect(described_class.min_volume(2500)).to contain_exactly(kw2, kw3)
        expect(described_class.min_volume(5000)).to contain_exactly(kw2)
      end

      it "returns all records when vol is blank or nil" do
        expect(described_class.min_volume(nil)).to contain_exactly(kw1, kw2, kw3)
        expect(described_class.min_volume("")).to contain_exactly(kw1, kw2, kw3)
      end
    end
  end

  describe ".calculate_score" do
    it "calculates score using the formula avg_monthly_searches * (1 - competition_index/100) * niche_fit" do
      score = described_class.calculate_score(avg_monthly_searches: 10_000, competition_index: 50, niche_fit: 1.0)
      expect(score).to be_within(0.01).of(5_000.0)
    end

    it "handles nil avg_monthly_searches safely returning 0.0" do
      score = described_class.calculate_score(avg_monthly_searches: nil, competition_index: 50)
      expect(score).to eq(0.0)
    end

    it "handles nil competition_index safely" do
      score = described_class.calculate_score(avg_monthly_searches: 10_000, competition_index: nil)
      expect(score).to be_within(0.01).of(10_000.0)
    end

    it "applies custom niche_fit multiplier" do
      score = described_class.calculate_score(avg_monthly_searches: 10_000, competition_index: 50, niche_fit: 0.8)
      expect(score).to be_within(0.01).of(4_000.0)
    end
  end

  describe "#calculate_score" do
    it "delegates to class method calculate_score using record attributes" do
      kw = build(:keyword, avg_monthly_searches: 20_000, competition_index: 25)
      expect(kw.calculate_score).to be_within(0.01).of(15_000.0)
      expect(kw.calculate_score(niche_fit: 0.5)).to be_within(0.01).of(7_500.0)
    end
  end
end
