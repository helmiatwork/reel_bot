class CreateVideoProjects < ActiveRecord::Migration[8.1]
  def change
    create_table :video_projects do |t|
      t.string :title, null: false
      t.string :topic
      t.string :hook
      t.jsonb :script, default: {}
      t.string :status, default: "draft", null: false

      t.timestamps
    end
    add_index :video_projects, :status
  end
end
