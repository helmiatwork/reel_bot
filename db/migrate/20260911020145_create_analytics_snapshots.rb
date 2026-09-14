class CreateAnalyticsSnapshots < ActiveRecord::Migration[8.1]
  def change
    create_table :analytics_snapshots do |t|
      t.references :pipeline_run, null: false, foreign_key: true
      t.references :channel_account, null: false, foreign_key: true
      t.integer :views, default: 0, null: false
      t.float :watch_time_minutes, default: 0.0, null: false
      t.integer :likes, default: 0, null: false
      t.integer :comments, default: 0, null: false
      t.float :ctr, default: 0.0, null: false
      t.jsonb :raw_payload, default: {}

      t.timestamps
    end
  end
end
