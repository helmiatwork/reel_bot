# frozen_string_literal: true

require "rails_helper"

RSpec.describe "Accounts", :regression, type: :request do
  let!(:account1) do
    create(
      :channel_account,
      platform: "youtube",
      account_name: "Channel One",
      account_identifier: "UC_channel_1",
      role: "main",
      brand_id: 10,
      credentials: { "token" => "secret_token_1", "cookies" => { "session" => "s1" } }
    )
  end

  let!(:account2) do
    create(
      :channel_account,
      platform: "tiktok",
      account_name: "Channel Two",
      account_identifier: "@tiktok_2",
      role: "clip",
      brand_id: 20,
      credentials: { "access_token" => "secret_token_2" }
    )
  end

  let!(:account3) do
    create(
      :channel_account,
      platform: "instagram",
      account_name: "Channel Three",
      account_identifier: "@insta_3",
      role: "creator",
      brand_id: 10,
      credentials: { "token" => "secret_token_3" }
    )
  end

  describe "GET /accounts" do
    it "lists accounts with default limit 50 and excludes sensitive credentials" do
      get "/accounts"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json.length).to eq(3)

      json.each do |item|
        expect(item).to have_key("id")
        expect(item).to have_key("platform")
        if item["credentials"].present?
          expect(item["credentials"]).not_to have_key("token")
          expect(item["credentials"]).not_to have_key("access_token")
          expect(item["credentials"]).not_to have_key("cookies")
        end
      end
    end

    it "filters by platform" do
      get "/accounts", params: { platform: "youtube" }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json.length).to eq(1)
      expect(json.first["platform"]).to eq("youtube")
      expect(json.first["account_name"]).to eq("Channel One")
    end

    it "filters by role" do
      get "/accounts", params: { role: "clip" }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json.length).to eq(1)
      expect(json.first["role"]).to eq("clip")
    end

    it "filters by brand_id" do
      get "/accounts", params: { brand_id: 10 }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json.length).to eq(2)
      expect(json.map { |a| a["brand_id"] }).to all(eq(10))
    end

    it "paginates with limit and offset" do
      get "/accounts", params: { limit: 1, offset: 1 }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json.length).to eq(1)
    end

    it "clamps limit between 1 and 100" do
      get "/accounts", params: { limit: 200 }
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json.length).to eq(3)
    end
  end

  describe "POST /accounts" do
    let(:valid_params) do
      {
        platform: "youtube",
        account_identifier: "UC_new_channel",
        account_name: "New Channel",
        role: "brand",
        brand_id: 42
      }
    end

    it "creates an account with standard params and returns 201 Created" do
      expect {
        post "/accounts", params: valid_params.to_json, headers: { "Content-Type" => "application/json" }
      }.to change(ChannelAccount, :count).by(1)

      expect(response).to have_http_status(:created)
      json = JSON.parse(response.body)
      expect(json["platform"]).to eq("youtube")
      expect(json["account_name"]).to eq("New Channel")
      expect(json["role"]).to eq("brand")
      expect(json["brand_id"]).to eq(42)
    end

    it "supports handle and label parameter aliases" do
      alias_params = {
        platform: "tiktok",
        handle: "@alias_handle",
        label: "Alias Label",
        role: "main"
      }

      expect {
        post "/accounts", params: alias_params.to_json, headers: { "Content-Type" => "application/json" }
      }.to change(ChannelAccount, :count).by(1)

      expect(response).to have_http_status(:created)
      created = ChannelAccount.find_by(account_identifier: "@alias_handle")
      expect(created).to be_present
      expect(created.label).to eq("Alias Label")
    end

    it "returns 422 Unprocessable Content on validation errors" do
      invalid_params = { platform: "unknown_platform", account_identifier: "UC_invalid" }
      post "/accounts", params: invalid_params.to_json, headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:unprocessable_content)
      json = JSON.parse(response.body)
      expect(json["errors"]).to be_present
    end
  end

  describe "PATCH /accounts/:id" do
    it "updates label, role, brand_id, and active" do
      patch "/accounts/#{account1.id}",
            params: { label: "Updated Title", role: "competitor", brand_id: 99, active: false }.to_json,
            headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:ok)
      account1.reload
      expect(account1.label).to eq("Updated Title")
      expect(account1.role).to eq("competitor")
      expect(account1.brand_id).to eq(99)
      expect(account1.active).to be(false)
    end

    it "returns 404 when account is not found" do
      patch "/accounts/999999",
            params: { label: "Updated" }.to_json,
            headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:not_found)
    end

    it "returns 422 on invalid update params" do
      patch "/accounts/#{account1.id}",
            params: { role: "invalid_role" }.to_json,
            headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:unprocessable_content)
    end
  end

  describe "DELETE /accounts/:id" do
    it "destroys the record and returns 200/204" do
      expect {
        delete "/accounts/#{account1.id}"
      }.to change(ChannelAccount, :count).by(-1)

      expect(response.status).to be_in([ 200, 204 ])
    end

    it "returns 404 when account is not found" do
      delete "/accounts/999999"
      expect(response).to have_http_status(:not_found)
    end
  end

  describe "POST /accounts/:id/cookies" do
    it "updates cookies with a hash payload and returns { status: \"ok\" }" do
      post "/accounts/#{account1.id}/cookies",
           params: { cookies: { session_token: "xyz_new_sess" } }.to_json,
           headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")

      account1.reload
      expect(account1.cookies).to eq({ "session_token" => "xyz_new_sess" })
    end

    it "updates cookies with a string payload" do
      post "/accounts/#{account1.id}/cookies",
           params: { cookies: "session_id=str_cookie" }.to_json,
           headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:ok)
      expect(account1.reload.cookies).to eq("session_id=str_cookie")
    end

    it "returns 404 when account is not found" do
      post "/accounts/999999/cookies",
           params: { cookies: "sess" }.to_json,
           headers: { "Content-Type" => "application/json" }

      expect(response).to have_http_status(:not_found)
    end
  end

  describe "DELETE /accounts/:id/cookies" do
    it "clears cookies from the account and returns { status: \"ok\" }" do
      delete "/accounts/#{account1.id}/cookies"
      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json["status"]).to eq("ok")

      account1.reload
      expect(account1.cookies).to be_nil
    end

    it "returns 404 when account is not found" do
      delete "/accounts/999999/cookies"
      expect(response).to have_http_status(:not_found)
    end
  end
end
