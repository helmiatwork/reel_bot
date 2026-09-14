# frozen_string_literal: true

class CreateSnoopTargets < ActiveRecord::Migration[8.1]
  def change
    create_table :snoop_targets do |t|
      t.string :channel_id, null: false
      t.string :handle
      t.string :last_seen_video_id

      t.timestamps
    end

    add_index :snoop_targets, :channel_id, unique: true
  end
end
