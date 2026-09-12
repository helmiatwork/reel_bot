# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[8.1].define(version: 2026_09_12_000707) do
  # These are extensions that must be enabled in order to support this database
  enable_extension "pg_catalog.plpgsql"

  create_table "analytics_snapshots", force: :cascade do |t|
    t.bigint "channel_account_id", null: false
    t.integer "comments", default: 0, null: false
    t.datetime "created_at", null: false
    t.float "ctr", default: 0.0, null: false
    t.integer "likes", default: 0, null: false
    t.bigint "pipeline_run_id", null: false
    t.jsonb "raw_payload", default: {}
    t.datetime "updated_at", null: false
    t.integer "views", default: 0, null: false
    t.float "watch_time_minutes", default: 0.0, null: false
    t.index ["channel_account_id"], name: "index_analytics_snapshots_on_channel_account_id"
    t.index ["pipeline_run_id"], name: "index_analytics_snapshots_on_pipeline_run_id"
  end

  create_table "channel_accounts", force: :cascade do |t|
    t.string "account_identifier", null: false
    t.string "account_name", null: false
    t.integer "brand_id"
    t.datetime "created_at", null: false
    t.jsonb "credentials", default: {}
    t.boolean "is_active", default: true, null: false
    t.string "platform", null: false
    t.string "role", default: "main", null: false
    t.datetime "updated_at", null: false
    t.index ["brand_id"], name: "index_channel_accounts_on_brand_id"
    t.index ["platform", "account_identifier"], name: "index_channel_accounts_on_platform_and_account_identifier", unique: true
    t.index ["role"], name: "index_channel_accounts_on_role"
  end

  create_table "pipeline_runs", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.text "error_message"
    t.string "final_video_path"
    t.jsonb "metadata", default: {}
    t.integer "quality_score"
    t.string "raw_video_path"
    t.string "run_id", null: false
    t.string "status", default: "pending", null: false
    t.string "subtitles_path"
    t.datetime "updated_at", null: false
    t.bigint "video_project_id", null: false
    t.index ["run_id"], name: "index_pipeline_runs_on_run_id", unique: true
    t.index ["status"], name: "index_pipeline_runs_on_status"
    t.index ["video_project_id"], name: "index_pipeline_runs_on_video_project_id"
  end

  create_table "video_projects", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.string "hook"
    t.jsonb "script", default: {}
    t.string "status", default: "draft", null: false
    t.string "title", null: false
    t.string "topic"
    t.datetime "updated_at", null: false
    t.index ["status"], name: "index_video_projects_on_status"
  end

  add_foreign_key "analytics_snapshots", "channel_accounts"
  add_foreign_key "analytics_snapshots", "pipeline_runs"
  add_foreign_key "pipeline_runs", "video_projects"
end
